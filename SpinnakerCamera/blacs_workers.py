#####################################################################
#                                                                   #
# /labscript_devices/SpinnakerCamera/blacs_workers.py             #
#                                                                   #
# Copyright 2019, Monash University and contributors                #
#                                                                   #
# This file is part of labscript_devices, in the labscript suite    #
# (see http://labscriptsuite.org), and is licensed under the        #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################

# Original imaqdx_camera server by dt, with modifications by rpanderson and cbillington.
# Refactored as a BLACS worker by cbillington
# Original PyCapture2_camera_server by dsbarker
# Ported to BLACS worker by dihm

import numpy as np
from labscript_utils import dedent
from enum import IntEnum
import PySpin

from labscript_devices.IMAQdxCamera.blacs_workers import IMAQdxCameraWorker

class Spinnaker_Camera(object):
    def __init__(self, serial_number):
        """Initialize Spinnaker API camera.

        Serial number should be of string(?) type."""
        self.system = PySpin.System.GetInstance()

        ver = self.system.GetLibraryVersion()
        min_ver = (1,23,0,27) # first release with python 3.6 support
        if (ver.major, ver.minor, ver.type, ver.build) < min_ver:
            raise RuntimeError(f"PySpin version {ver} must be >= {min_ver}")

        camList = self.system.GetCameras()
        numCams = camList.GetSize()

        if numCams==0:
            raise ValueError('No cameras found!')

        if isinstance(serial_number, int):
            self.camera = camList.GetBySerial('%d' % serial_number)
        else:
            self.camera = camList.GetBySerial(serial_number)
        self.camera.Init()
        camList.Clear()

        # Set the timeout to 5 s:
        self.timeout = 5000 # in ms

        # Set the abort acquisition thingy:
        self._abort_acquisition = False

    def get_attribute_names(self, visibility):
        names = []
        def get_node_names_in_category(node_category, prefix=''):
            for node_feature in node_category.GetFeatures():
                # Ensure node is available and readable
                if (not PySpin.IsAvailable(node_feature) or not
                    PySpin.IsReadable(node_feature)):
                    continue

                # Get the feature name:
                feature_name = node_feature.GetName()

                # Category nodes must be dealt with separately in order to retrieve subnodes recursively.
                if node_feature.GetPrincipalInterfaceType() == PySpin.intfICategory:
                    get_node_names_in_category(PySpin.CCategoryPtr(node_feature),
                                               prefix=feature_name + '::')
                else:
                    names.append(prefix + feature_name)

        node = self.camera.GetNodeMap()
        get_node_names_in_category(PySpin.CCategoryPtr(node.GetNode('Root')))

        return names

    def get_attribute(self, name):
        """Return current values dictionary of attribute of the given name"""
        name = name.split('::')

        nodemap = self.camera.GetNodeMap()
        node = nodemap.GetNode(name[-1])

        if PySpin.IsAvailable(node) and PySpin.IsReadable(node):
            if node.GetPrincipalInterfaceType() == PySpin.intfIInteger:
                return PySpin.CIntegerPtr(node).GetValue()
            elif node.GetPrincipalInterfaceType() == PySpin.intfIFloat:
                return PySpin.CFloatPtr(node).GetValue()
            elif node.GetPrincipalInterfaceType() == PySpin.intfIBoolean:
                return PySpin.CBooleanPtr(node).GetValue()
            else:
                return PySpin.CValuePtr(node).ToString()

    def set_attributes(self, attr_dict):
        for k, v in attr_dict.items():
            self.set_attribute(k, v)

    def set_stream_attribute(self, name, value):
        self.set_attribute(name, value, stream_map=True)

    def set_attribute(self, name, value, stream_map=False):
        name = name.split('::')

        if stream_map:
            nodemap = self.camera.GetTLStreamNodeMap()
        else:
            nodemap = self.camera.GetNodeMap()
        node = nodemap.GetNode(name[-1])

        if PySpin.IsAvailable(node) and PySpin.IsWritable(node):
            if node.GetPrincipalInterfaceType() == PySpin.intfIInteger:
                 PySpin.CIntegerPtr(node).SetValue(value)
            elif node.GetPrincipalInterfaceType() == PySpin.intfIFloat:
                 PySpin.CFloatPtr(node).SetValue(value)
            elif node.GetPrincipalInterfaceType() == PySpin.intfIBoolean:
                PySpin.CBooleanPtr(node).SetValue(value)
            else:
                PySpin.CValuePtr(node).FromString(value)

    def snap(self):
        """Acquire a single image and return it"""
        self.configure_acquisition(continuous=False, bufferCount=1)
        image = self.grab()
        self.camera.EndAcquisition()
        return image

    def grab(self):
        """Grab and return single image during pre-configured acquisition."""
        #print('Grabbing...')
        image_result = self.camera.GetNextImage(self.timeout)
        img = self._decode_image_data(image_result.GetData())
        image_result.Release()
        return img

    def grab_multiple(self, n_images, images):
        """Grab n_images into images array during buffered acquistion."""
        print(f"Attempting to grab {n_images} images.")
        for i in range(n_images):
            if self._abort_acquisition:
                print("Abort during acquisition.")
                self._abort_acquisition = False
                return

            images.append(self.grab())
            print(f"Got image {i+1} of {n_images}.")
        print(f"Got {len(images)} of {n_images} images.")

    def configure_acquisition(self, continuous=True, bufferCount=10):
        self.pix_fmt = self.get_attribute('PixelFormat')
        self.height = self.get_attribute('Height')
        self.width = self.get_attribute('Width')

        # Might need to do something more fancy with the buffering, but
        # for the moment, I anticipate this will work.
        if continuous:
            self.set_stream_attribute('StreamBufferCountMode', 'Manual')
            self.set_stream_attribute('StreamBufferCountManual', 10)
            self.set_stream_attribute('StreamBufferHandlingMode', 'NewestFirst')
            self.set_attribute('AcquisitionMode', 'Continuous')
        elif bufferCount == 1:
            self.set_stream_attribute('StreamBufferCountMode', 'Auto')
            self.set_stream_attribute('StreamBufferHandlingMode', 'OldestFirst')
            self.set_attribute('AcquisitionMode', 'SingleFrame')
        else:
            self.set_stream_attribute('StreamBufferCountMode', 'Auto')
            self.set_stream_attribute('StreamBufferHandlingMode', 'OldestFirst')
            self.set_attribute('AcquisitionMode', 'MultiFrame')
            self.set_attribute('AcquisitionFrameCount', bufferCount)

        self.camera.BeginAcquisition()

    def _decode_image_data(self, img):
        """Spinnaker image buffers require significant formatting.
        This returns what one would expect from a camera.
        configure_acquisition must be called first to set image format parameters."""
        if self.pix_fmt.startswith('Mono'):
            if self.pix_fmt.endswith('8'):
                dtype = 'uint8'
            else:
                dtype = 'uint16'
            image = np.frombuffer(img, dtype=dtype).reshape(self.height, self.width)
        else:
            msg = """Only MONO image types currently supported.
            To add other image types, add conversion logic from returned
            uint8 data to desired format in _decode_image_data() method."""
            raise ValueError(dedent(msg))
        return image.copy()

    def stop_acquisition(self):
        print('Stopping acquisition...')
        self.camera.EndAcquisition()

    def abort_acquisition(self):
        print('Stopping acquisition...')
        self._abort_acquisition = True

    def close(self):
        print('Closing down the camera...')
        self.camera.DeInit()
        #self.camList.Clear()
        self.system.ReleaseInstance()


class SpinnakerCameraWorker(IMAQdxCameraWorker):
    """Spinnaker API Camera Worker.

    Inherits from IMAQdxCameraWorker. Overloads get_attributes_as_dict
    to use SpinnakerCamera.get_attributes() method."""
    interface_class = Spinnaker_Camera

    """def get_attributes_as_dict(self, visibility_level):
        # Return a dict of the attributes of the camera for the given visibility
        # level
        return self.camera.get_attributes(visibility_level)"""
