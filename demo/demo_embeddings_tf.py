'''
Reads texts from file and for each line generates N imagess conditioned on text
'''
from __future__ import division
from __future__ import print_function

import prettytensor as pt
import tensorflow as tf
import numpy as np
import scipy.misc
import os
import argparse
from PIL import Image, ImageDraw, ImageFont
import re

from misc.config import cfg, cfg_from_file
from misc.utils import mkdir_p
from stageII.model import CondGAN

from embedding.model import Model
from embedding.preprocessing import normalize


def parse_args():
    parser = argparse.ArgumentParser(description='Train a GAN network')
    parser.add_argument('--cfg', dest='cfg_file',
                        help='optional config file',
                        default=None, type=str)
    parser.add_argument('--gpu', dest='gpu_id',
                        help='GPU device id to use [0]',
                        default=-1, type=int)

    parser.add_argument('--caption_path', type=str, default=None,
                        help='Path to the file with text sentences')

    parser.add_argument('--caption_model', type=str, default=None,
                        help='Path to the file with embedding model')

    parser.add_argument('--save_dir', type=str, default=None,
                        help='Path to output saved images')
    args = parser.parse_args()
    return args


def sample_encoded_context(embeddings, model, bAugmentation=True):
    '''Helper function for init_opt'''
    # Build conditioning augmentation structure for text embedding
    # under different variable_scope: 'g_net' and 'hr_g_net'
    c_mean_logsigma = model.generate_condition(embeddings)
    mean = c_mean_logsigma[0]
    if bAugmentation:
        # epsilon = tf.random_normal(tf.shape(mean))
        epsilon = tf.truncated_normal(tf.shape(mean))
        stddev = tf.exp(c_mean_logsigma[1])
        c = mean + stddev * epsilon
    else:
        c = mean
    return c


def build_model(sess, embedding_dim, batch_size, cfg):
    '''
    Builds model
    '''

    hr_lr_ratio = int(cfg.TEST.HR_IMSIZE / cfg.TEST.LR_IMSIZE)
    model = CondGAN(
        lr_imsize=cfg.TEST.LR_IMSIZE,
        hr_lr_ratio=hr_lr_ratio)

    embeddings = tf.placeholder(
        tf.float32, [batch_size, embedding_dim],
        name='conditional_embeddings')

    with pt.defaults_scope(phase=pt.Phase.test):
        with tf.variable_scope("g_net"):
            c = sample_encoded_context(embeddings, model)
            z = tf.random_normal([batch_size, cfg.Z_DIM])
            fake_images = model.get_generator(tf.concat(1, [c, z]))
        with tf.variable_scope("hr_g_net"):
            hr_c = sample_encoded_context(embeddings, model)
            hr_fake_images = model.hr_get_generator(fake_images, hr_c)

    ckt_path = cfg.TEST.PRETRAINED_MODEL
    if ckt_path.find('.ckpt') != -1:
        print("Reading model parameters from %s" % ckt_path)
        saver = tf.train.Saver(tf.all_variables())
        saver.restore(sess, ckt_path)
    else:
        print("Input a valid model path. %s is not valid" % ckt_path)
    return embeddings, fake_images, hr_fake_images


def drawCaption(img, caption):
    img_txt = Image.fromarray(img)
    # get a font
    fnt = ImageFont.truetype('Pillow/Tests/fonts/FreeMono.ttf', 50)
    # get a drawing context
    d = ImageDraw.Draw(img_txt)

    d.text((10, 256), 'Stage-I', font=fnt, fill=(0, 0, 0, 255))
    d.text((10, 512), 'Stage-II', font=fnt, fill=(0, 0, 0, 255))
    if img.shape[0] > 832:
        d.text((10, 832), 'Stage-I', font=fnt, fill=(0, 0, 0, 255))
        d.text((10, 1088), 'Stage-II', font=fnt, fill=(0, 0, 0, 255))

    idx = caption.find(' ', 60)
    if idx == -1:
        d.text((256, 10), caption, font=fnt, fill=(0, 0, 0, 255))
    else:
        cap1 = caption[:idx]
        cap2 = caption[idx + 1:]
        d.text((256, 10), cap1, font=fnt, fill=(0, 0, 0, 255))
        d.text((256, 60), cap2, font=fnt, fill=(0, 0, 0, 255))

    return img_txt


def save_super_images(lr_sample_batchs, hr_sample_batchs,
                      texts_batch, batch_size,
                      startID, save_dir=None):

    if save_dir and not os.path.isdir(save_dir):
        print('Make a new folder: ', save_dir)
        mkdir_p(save_dir)

    # Save up to 16 samples for each text embedding/sentence
    img_shape = hr_sample_batchs[0][0].shape
    super_images = []
    for j in range(batch_size):
        if not re.search('[a-zA-Z]+', texts_batch[j]):
            continue

        padding = 255 + np.zeros(img_shape)
        row1 = [padding]
        row2 = [padding]
        # First row with up to 8 samples
        for i in range(np.minimum(8, len(lr_sample_batchs))):
            lr_img = lr_sample_batchs[i][j]
            hr_img = hr_sample_batchs[i][j]
            hr_img = (hr_img + 1.0) * 127.5
            re_sample = scipy.misc.imresize(lr_img, hr_img.shape[:2])
            row1.append(re_sample)
            row2.append(hr_img)
        row1 = np.concatenate(row1, axis=1)
        row2 = np.concatenate(row2, axis=1)
        superimage = np.concatenate([row1, row2], axis=0)

        # Second 8 samples with up to 8 samples
        if len(lr_sample_batchs) > 8:
            row1 = [padding]
            row2 = [padding]
            for i in range(8, len(lr_sample_batchs)):
                lr_img = lr_sample_batchs[i][j]
                hr_img = hr_sample_batchs[i][j]
                hr_img = (hr_img + 1.0) * 127.5
                re_sample = scipy.misc.imresize(lr_img, hr_img.shape[:2])
                row1.append(re_sample)
                row2.append(hr_img)
            row1 = np.concatenate(row1, axis=1)
            row2 = np.concatenate(row2, axis=1)
            super_row = np.concatenate([row1, row2], axis=0)
            superimage2 = np.zeros_like(superimage)
            superimage2[:super_row.shape[0],
                        :super_row.shape[1],
                        :super_row.shape[2]] = super_row
            mid_padding = np.zeros((64, superimage.shape[1], 3))
            superimage =\
                np.concatenate([superimage, mid_padding, superimage2], axis=0)

        top_padding = 255 + np.zeros((128, superimage.shape[1], 3))
        superimage =\
            np.concatenate([top_padding, superimage], axis=0)

        fullpath = '%s/sentence%d.jpg' % (save_dir, startID + j)
        superimage = drawCaption(np.uint8(superimage), texts_batch[j])
        if save_dir:
            scipy.misc.imsave(fullpath, superimage)
        super_images.append(superimage)

    return super_images


def embed_text(texts_path, model_path):
    print('Loading texts')
    with open(texts_path, 'rt') as f:
        texts = f.readlines()

    print('Loading embedding model')
    model = Model(
        os.path.join(model_path, 'frozen_model.pb'),
        os.path.join(model_path, 'tokenizer.pickle')
    )

    normalized_texts = [normalize(text) for text in texts]
    embeddings = model.embed(normalized_texts)

    num_embeddings = len(normalized_texts)
    print('Successfully load sentences from: ', texts_path)
    print('Total number of sentences:', num_embeddings)
    print('num_embeddings:', num_embeddings, embeddings.shape)

    return embeddings, num_embeddings, normalized_texts


class GenerativeModel(object):
    def __init__(self, cfg, batch_size, embedding_dim):
        config = tf.ConfigProto(allow_soft_placement=True)
        self.persistent_sess = tf.Session(config=config)
        self.batch_size = batch_size
        with tf.device("/gpu:%d" % cfg.GPU_ID):
            self.embeddings_holder, self.fake_images_opt, self.hr_fake_images_opt =\
                build_model(self.persistent_sess, embedding_dim, self.batch_size, cfg)

    def __del__(self):
        self.persistent_sess.close()

    def generate(self, embeddings):
        hr_samples, lr_samples =\
            self.persistent_sess.run(
                [self.hr_fake_images_opt, self.fake_images_opt],
                feed_dict={
                    self.embeddings_holder: embeddings
                })

        return hr_samples, lr_samples

    def generate_n(self, embeddings, n=8):
        lr_samples_batchs = []
        hr_samples_batchs = []

        for i in range(np.minimum(16, n)):
            hr_samples, samples = self.generate(embeddings)
            lr_samples_batchs.append(samples)
            hr_samples_batchs.append(hr_samples)

        return hr_samples_batchs, lr_samples_batchs


if __name__ == "__main__":
    args = parse_args()

    if args.cfg_file is not None:
        cfg_from_file(args.cfg_file)
    if args.gpu_id != -1:
        cfg.GPU_ID = args.gpu_id
    if args.caption_path is not None:
        cfg.TEST.CAPTION_PATH = args.caption_path

    # generate embeddings
    embeddings, num_embeddings, normalized_texts = embed_text(
        args.caption_path,
        args.caption_model)

    if num_embeddings <= 0:
        raise ValueError('At least one embedding required')

    # set batchs size
    batch_size = np.minimum(num_embeddings, cfg.TEST.BATCH_SIZE)

    # create model
    model = GenerativeModel(cfg, batch_size, embeddings.shape[-1])
    # path to save generated samples
    save_dir = args.save_dir if args.save_dir else os.path.dirname(
        args.caption_path)

    # Build StackGAN and load the model

    count = 0
    while count < num_embeddings:
        # generate batches
        iend = count + batch_size
        if iend > num_embeddings:
            iend = num_embeddings
            count = num_embeddings - batch_size
        embeddings_batch = embeddings[count:iend]
        text_batch = normalized_texts[count:iend]

        # sample images
        hr_samples_batch, lr_samples_batch = model.generate_n(embeddings_batch)
        super_images = save_super_images(
            lr_samples_batch,
            hr_samples_batch,
            text_batch,
            batch_size,
            startID=count, save_dir=save_dir)

        count += batch_size

    print('Finish generating samples for %d sentences:' % num_embeddings)
    print('Example sentences:')
    for i in range(np.minimum(10, num_embeddings)):
        print('Sentence %d: %s' % (i, normalized_texts[i]))
