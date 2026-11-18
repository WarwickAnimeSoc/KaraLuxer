#!/usr/bin/env python3

"""
@file          classification.py
@brief         determine the pitch by analysing the provided data
@author        paradigm
"""

import os
os.environ['ORT_DISABLE_TELEMETRY'] = "1"
import numpy as np
import onnxruntime as rt

rt.disable_telemetry_events()

class PitchClassifier:
    """ determines pitch by a trained neuronal network """

    def __init__(self, model: str):
        """ load and init onnx model """
        sess_options = rt.SessionOptions()
        # enable parallel graph execution
        sess_options.execution_mode = rt.ExecutionMode.ORT_PARALLEL
        # optimize graph at runtime
        sess_options.graph_optimization_level = (
            rt.GraphOptimizationLevel.ORT_ENABLE_ALL
        )
        # load model from external source
        self.sess = rt.InferenceSession(model, sess_options)
        self.input_name = self.sess.get_inputs()[0].name

    def predict(self, X: np.ndarray) -> np.ndarray:
        """ predict pitch probabilities from a given feature set (batch_size, feature_size) """
        return self.sess.run(None, {self.input_name: X.astype(np.float32)})[0]
