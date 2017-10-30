import json
import os
import sys

import numpy as np
import tensorflow as tf
import pickle

from keras.preprocessing.sequence import pad_sequences
from keras.preprocessing.text import Tokenizer

INPUT_TENSOR_NAME='embedding_1_input:0'
OUTPUT_TENSOR_NAME='embedding/Relu:0'
LEARNING_PAHSE='dropout_1/keras_learning_phase:0'

PREFIX ='prefix'
MAX_SENT_LENGTH = 400


def load_graph(frozen_graph_filename):
    ''' loads serialized tensorflow graph '''

    # load the protobuf file from the disk and parse it to 
    # retrieve the unserialized graph_def
    with tf.gfile.GFile(frozen_graph_filename, "rb") as f:
        graph_def = tf.GraphDef()
        graph_def.ParseFromString(f.read())

    # Then, we import the graph_def into a new Graph and returns it 
    with tf.Graph().as_default() as graph:
        # The name var will prefix every op/nodes in your graph
        # Since we load everything in a new graph, this is not needed
        tf.import_graph_def(graph_def, name=PREFIX)

    return graph


class Model(object):
    '''
    Wrapper to embed text using trained model and tokenizer
    '''
    def __init__(self, frozen_graph_filename, tokenizer_path, maxlen=MAX_SENT_LENGTH):
        print('Loading the graph')
        graph = load_graph(frozen_graph_filename)
        self.X = graph.get_tensor_by_name("%s/%s" % (PREFIX, INPUT_TENSOR_NAME))
        self.Y = graph.get_tensor_by_name("%s/%s" % (PREFIX, OUTPUT_TENSOR_NAME))
        self.LF = graph.get_tensor_by_name("%s/%s" % (PREFIX, LEARNING_PAHSE))

        self.tokenizer = pickle.load(open(tokenizer_path, 'rb'))
        self.persistent_sess = tf.Session(graph=graph)
        self.maxlen = maxlen

    def embed(self, text):
        ''' use model to find prediction '''
        # our graph expect tensors of shape '(?, 1)'
        if not isinstance(text, (list, tuple)):
            text = [text]

        x = self.tokenizer.texts_to_sequences(text)
        x = pad_sequences(x, maxlen=self.maxlen, padding='post', truncating='post')
        x = np.array(x).reshape(-1, self.maxlen)
        h = self.persistent_sess.run(self.Y, feed_dict={
            self.X: x,
            self.LF:  False
        })

        return h
