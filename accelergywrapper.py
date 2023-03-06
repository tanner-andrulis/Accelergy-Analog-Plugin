import logging
import sys
import os
import re
from typing import Dict
import yaml
from accelergy.plug_in_interface.interface import *

# Need to add this directory to path for proper imports
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.append(SCRIPT_DIR)
from optimizer import ADCRequest
from headers import *

MODEL_FILE = os.path.join(SCRIPT_DIR, 'adc_data/model.yaml')
AREA_ACCURACY = 75
ENERGY_ACCURACY = 75

CLASS_NAMES = ['adc', 'pim_adc', 'sar_adc']
ACTION_NAMES = ['convert', 'drive', 'read', 'sample']

# ==============================================================================
# Input Parsing
# ==============================================================================
def unit_check(key, attributes, default, my_scale, accelergy_scale):
    """ Checks for a key in attributes & does unit conversions """
    if key not in attributes:
        return default
    try:
        return float(attributes[key]) / my_scale * accelergy_scale
    except ValueError:
        pass

    v = re.findall(r'(\d*\.?\d+|\d+\.?\d*)', attributes[key])
    if not v:
        return default
    v = float(v[0]) / my_scale

    nounit = True
    for index, postfix in enumerate(['', 'm', 'u', 'n', 'p', 'f']):
        if postfix in attributes[key]:
            nounit = False
            v /= (1000 ** index)
    if nounit:
        v *= accelergy_scale
    return v


def adc_attr_to_request(attributes: Dict, logger: logging.Logger) -> ADCRequest:
    """ Creates an ADC Request from a list of attributes """

    def checkerr(attr, numeric):
        assert attr in attributes, f'No attribute found: {attr}'
        if numeric and isinstance(attributes[attr], str):
            v = re.findall(r'(\d*\.?\d+|\d+\.?\d*)', attributes[attr])
            assert v, f'No numeric found for attribute: {attr}'
            return float(v[0])
        return attributes[attr]

    try:
        n_adc = int(  checkerr('n_adc', numeric=True))
    except AssertionError:
        n_adc = int(  checkerr('n_components', numeric=True))

    r = ADCRequest(
        bits                 =float(checkerr('resolution', numeric=True)),
        tech                 =float(checkerr('technology', numeric=True)),
        throughput           =float(checkerr('throughput', numeric=True)),
        n_adc                =n_adc,
        logger               =logger,
    )
    return r


def dict_to_str(attributes: Dict) -> str:
    """ Converts a dictionary into a multi-line string representation """
    s = '\n'
    for k, v in attributes.items():
        s += f'\t{k}: {v}\n'
    return s


# ==============================================================================
# Wrapper Class
# ==============================================================================
class AnalogEstimator(AccelergyPlugIn):
    def __init__(self):
        self.estimator_name = 'Analog Estimator'
        if not os.path.exists(MODEL_FILE):
            self.logger.info(f'python3 {os.path.join(SCRIPT_DIR, "run.py")} -g')
            os.system(f'python3 {os.path.join(SCRIPT_DIR, "run.py")} -g')
        if not os.path.exists(MODEL_FILE):
            self.logger.error(f'ERROR: Could not find model file: {MODEL_FILE}')
            self.logger.error(f'Try running: "python3 {os.path.join(SCRIPT_DIR, "run.py")} '
                              f'-g" to generate a model.')
        with open(MODEL_FILE, 'r') as f:
            self.model = yaml.safe_load(f)

    def get_name(self) -> str:
        return self.estimator_name

    def primitive_action_supported(self, query: AccelergyQuery) -> AccuracyEstimation:
        class_name = query.class_name
        attributes = query.class_attrs
        action_name = query.action_name
        arguments = query.action_args


        if str(class_name).lower() == 'adc' and str(action_name).lower() == 'convert':
            adc_attr_to_request(attributes, self.logger)  # Errors if no match
            return AccuracyEstimation(ENERGY_ACCURACY)
        return AccuracyEstimation(0)  # if not supported, accuracy is 0

    def estimate_energy(self, query: AccelergyQuery) -> Estimation:
        class_name = query.class_name
        attributes = query.class_attrs
        action_name = query.action_name
        arguments = query.action_args

        if str(class_name).lower() not in CLASS_NAMES or \
            str(action_name).lower() not in ACTION_NAMES:
            raise NotImplementedError(f'Energy estimation for {class_name}.{action_name}'
                                    f'is not supported.')

        r = adc_attr_to_request(attributes, self.logger)  # Errors if no match
        self.logger.info(f'Accelergy requested ADC energy'
                            f' estimation with attributes: {dict_to_str(attributes)}')
        energy_per_op = r.energy_per_op(self.model) * 1e12  # J to pJ
        assert energy_per_op, 'Could not find ADC for request.'
        self.logger.info(f'Generated model uses {energy_per_op:2E} pJ/op.')
        return Estimation(energy_per_op, 'p') # energy is in pJ)

    def primitive_area_supported(self, query: AccelergyQuery) -> AccuracyEstimation:
        class_name = query.class_name
        attributes = query.class_attrs
        action_name = query.action_name
        arguments = query.action_args

        if str(class_name).lower() in CLASS_NAMES:
            adc_attr_to_request(attributes, self.logger)  # Errors if no match
            return AccuracyEstimation(AREA_ACCURACY)
        return AccuracyEstimation(0)  # if not supported, accuracy is 0

    def estimate_area(self, query: AccelergyQuery) -> Estimation:
        class_name = query.class_name
        attributes = query.class_attrs
        action_name = query.action_name
        arguments = query.action_args

        if str(class_name).lower() not in CLASS_NAMES:
            raise NotImplementedError(f'Area estimation for {class_name} is not supported.')

        r = adc_attr_to_request(attributes, self.logger)  # Errors if no match
        self.logger.info(f'Accelergy requested ADC energy'
                            f' estimation with attributes: {dict_to_str(attributes)}')
        area = r.area(self.model) # um^2 -> mm^2
        self.logger.info(f'Generated model uses {area:2E} um^2 total.')
        return Estimation(area, 'u^2') # area is in um^2

if __name__ == '__main__':
    bits = 8
    technode = 16
    throughput = 512e7
    n_adc = 32
    attrs = {
        'class_name': 'ADC',
        'action_name': 'convert',
        'attributes': {
            'resolution': bits,
            'technology': technode,
            'throughput': throughput,
            'n_adc': n_adc
        }
    }
    e = AnalogEstimator()
    e.estimate_energy(attrs)
    e.estimate_area(attrs)
