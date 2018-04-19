#####################################################################
#                                                                   #
# labscript_devices/ZaberStageController.py                         #
#                                                                   #
# Copyright 2013, Monash University                                 #
#                                                                   #
# This file is part of labscript_devices, in the labscript suite    #
# (see http://labscriptsuite.org), and is licensed under the        #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################

from __future__ import print_function, division, unicode_literals, absolute_import
from labscript_utils import PY2
if PY2:
    str = unicode
from labscript_devices import labscript_device, BLACS_tab, BLACS_worker
from labscript import StaticAnalogQuantity, Device, LabscriptError, set_passed_properties
import numpy as np
#import visa

@labscript_device
class GP370(Device):
    @set_passed_properties(property_names = {"connection_table_properties" : ["visa_resource"]})
    def __init__(self, name, visa_resource = ""):
        Device.__init__(self, name, None, None)
        self.BLACS_connection = visa_resource

    def generate_code(self, hdf5_file):
        self.init_device_group(hdf5_file) # Initialize group to ensure transition_to_buffered
                                          # occurs.

import os

from qtutils.qt.QtCore import *
from qtutils.qt.QtGui import *

from blacs.tab_base_classes import Worker, define_state
from blacs.tab_base_classes import MODE_MANUAL, MODE_TRANSITION_TO_BUFFERED, MODE_TRANSITION_TO_MANUAL, MODE_BUFFERED

from blacs.device_base_class import DeviceTab

from qtutils import UiLoader
import qtutils.icons

@BLACS_tab
class GP370ControllerTab(DeviceTab):
    def initialise_GUI(self):
        # Capabilities
        layout = self.get_tab_layout()
        ui_filepath = os.path.join(os.path.dirname(os.path.realpath(__file__)),'GP370.ui')
        self.ui = UiLoader().load(ui_filepath)
        layout.addWidget(self.ui)

        self.visa_resource =  self.settings['connection_table'].find_by_name(self.device_name).BLACS_connection
        self.ui.visa_resource_label.setText(self.visa_resource)

        self.ui.check_connectivity_pushButton.setIcon(QIcon(':/qtutils/fugue/arrow-circle'))
        self.ui.check_connectivity_pushButton.clicked.connect(self.check_connection_and_read_pressure)

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def check_connection_and_read_pressure(self, *args):
        icon = QIcon(':/qtutils/fugue/hourglass')
        pixmap = icon.pixmap(QSize(16, 16))
        status_text = 'Checking...'
        self.ui.status_icon.setPixmap(pixmap)
        self.ui.connection_status.setText(status_text)

        value = yield(self.queue_work(self.primary_worker, 'read_pressure'))
        self.ui.current_pressure.setText("{0:.2E}".format(value))\

        status_text = 'Working!'
        icon = QIcon(':/qtutils/fugue/tick')
        pixmap = icon.pixmap(QSize(16, 16))
        self.ui.status_icon.setPixmap(pixmap)
        self.ui.connection_status.setText(status_text)

    def initialise_workers(self):
        # Create and set the primary worker
        self.create_worker("main_worker",GP370Worker,{'visa_resource':self.visa_resource})
        self.primary_worker = "main_worker"

@BLACS_worker
class GP370Worker(Worker):
    def init(self):
        # TODO: Make this configurable
        self.response_timeout = 10 #seconds

        global visa; import visa
        global h5py; import labscript_utils.h5_lock, h5py
        global Queue; import Queue
        global time; import time
        global threading; import threading

        self.connection = visa.ResourceManager().open_resource(self.visa_resource)
        self.connection.timeout = 800 # set timeout in ms

        # On initilaization, do we wan to check for response?
        # response = True
        # while response is not None:
        #    response = self.connection.query()

    def program_manual(self, values):
        return {} # Return empty dict since there are no values.

    def read_pressure(self):
        return np.float32(self.connection.query('DS IG'))
        # TODO: some basic error checking

    def transition_to_buffered(self, device_name, h5file, initial_values, fresh):
        self.h5file = h5file
        try:
            self.init_pressure = self.read_pressure()
        except visa.VisaIOError as e:
            if str(e).startswith('VI_ERROR_TMO'):
                self.init_pressure = np.nan
            else:
                raise e
        self.device_name = device_name
        self.comm_queue = Queue.Queue()
        self.results_queue = Queue.Queue()
        start_time = time.time()
        self.read_thread = threading.Thread(target = self.read_loop, args = (self.comm_queue, self.results_queue, start_time))
        self.read_thread.daemon=True
        self.read_thread.start()
        return {}

    def transition_to_manual(self):
        self.comm_queue.put('exit')
        timed_data = self.results_queue.get(timeout=2)
        try:
            self.final_pressure = self.read_pressure()
        except visa.VisaIOError as e:
            if str(e).startswith('VI_ERROR_TMO'):
                self.final_pressure = np.nan
            else:
                raise e
        p_data = np.array([self.init_pressure, self.final_pressure])
        with h5py.File(self.h5file) as hdf5_file:
            group = hdf5_file.create_group('/data/'+ self.device_name)
            group.create_dataset('Pressure', data = p_data)
            try:
                measurements = hdf5_file['/data/traces']
            except:
                # Group doesn't exist yet, create it:
                measurements = hdf5_file.create_group('/data/traces')
            dset = measurements.create_dataset('Pressures', \
            (timed_data['t'].shape[0],), dtype = \
            np.dtype([("t", np.float32), ("values", np.float32)]))
            dset['t'] = timed_data['t']
            dset['values'] = timed_data['values']
        self.read_thread.join(1.0)
        self.comm_queue.get(timeout=1)
        return True

    def abort_buffered(self):
        return True

    def abort_transition_to_buffered(self):
        return True

    def shutdown(self):
        self.connection.close()
        return

    def read_loop(self, command_queue, results_queue, start_time):
        pressures = []
        times = []
        while command_queue.empty():
            try:
                pressures.append(self.read_pressure())
                times.append(time.time()-start_time)
            except visa.VisaIOError as e:
                if str(e).startswith('VI_ERROR_TMO'):
                    pass
                else:
                    raise e
            time.sleep(0.5)
        p_return = np.array(pressures)
        t_return = np.array(times)
        data_return = {'t' : t_return, 'values' : p_return}
        results_queue.put(data_return)
