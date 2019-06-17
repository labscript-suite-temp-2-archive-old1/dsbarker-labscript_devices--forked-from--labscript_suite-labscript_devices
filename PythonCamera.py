#####################################################################
#                                                                   #
# /labscript_devices/PythonCamera.py                                #
#                                                                   #
# Copyright 2013, Monash University                                 #
#                                                                   #
# This file is part of labscript_devices, in the labscript suite    #
# (see http://labscriptsuite.org), and is licensed under the        #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################
from __future__ import print_function, unicode_literals, absolute_import, division

try:
    from labscript_utils import check_version
except ImportError:
    raise ImportError('Require labscript_utils > 2.1.0')

check_version('labscript', '2.0.1', '3')

from labscript_devices import BLACS_tab
from labscript_devices.Camera import Camera, CameraTab
from labscript import set_passed_properties


class PythonCamera(Camera):
    """A class for new features not compatible with the legacy Camera class"""
    description = 'Python camera'

    @set_passed_properties(
        property_names = {
            "device_properties": ["acquisition_ROI", "pixel_size", "magnification",
                                  "quantum_efficiency", "bit_depth", "NA", "transmission",
                                  "counts_per_photoelectron"]}
        )

    def __init__(self, *args, **kwargs):
        self.acquisition_ROI = kwargs.pop('acquisition_ROI', None)
        self.pixel_size = kwargs.pop('pixel_size', 0.)
        self.magnification = kwargs.pop('magnification', 0.)
        self.quantum_efficiency = kwargs.pop('quantum_efficiency', 0.)
        self.transmission = kwargs.pop('transmission', 0.)
        self.counts_per_photoelectron = kwargs.pop('counts_per_photoelectron', 0.)
        self.bit_depth = kwargs.pop('bit_depth', 10.)
        self.NA = kwargs.pop('NA', 0.)
        self.videos = []
        self.frames = {}

        Camera.__init__(self, *args, **kwargs)

    def set_acquisition_ROI(self, acquisition_ROI):
        # acq_ROI is a tuple of form (width, height, offset_X, offset_Y) This
        # method can be used in a script to overwrite a camera's acquisition_ROI
        # after instantiation, so that BlACS does not detect a connection table
        # change on disk when the same file is being imported by experiment scripts
        # and used as the lab connection table.
        self.set_property('acquisition_ROI', acquisition_ROI,
                          location='device_properties', overwrite=True)


    def video(self, name, t, video_length, time_between_frames, exposure_time=None): #This makes it from 57 --> 32 lines and is more efficient
        if exposure_time is None:
            shutter_duration = self.exposure_time
        else:
            shutter_duration = exposure_time

        if shutter_duration is None:
            raise LabscriptError('Camera %s has not had an exposure_time set as an instantiation argument, '%self.name +
                                 'and one was not specified for this exposure')
        if not shutter_duration > 0:
            raise LabscriptError("exposure_time must be > 0, not %s"%str(duration))

        if time_between_frames > (exposure_time):
            raise LabscriptError("The time between frames has to be greater than the exposure time")

        if time_between_frames < 0:
            raise LabscriptError("The time between frames must be > 0, not %s"%str(time_between_frames))

        #num_frames = video_length / (shutter_duration + time_between_frames) #isn't used right now, idk what it can be used for
        videoFrames = range(start, end, time_between_frames) #Note that the Camera will not take a frame @ t + video_length
        num_frames = 0

        # Only ask for a trigger if one has not already been requested by
        # another camera attached to the same trigger:
        already_requested = False
        for videoFrame in videoFrames: # change j's to videoFrame:
            for camera in self.trigger_device.child_devices:
                if camera is not self:
                    if camera.frames: #might not be necessary
                        #If the next line throws an error just throw it under: if videoFrame in camera.frames
                        if camera.frames.get(videoFrame) == duration:
                            already_requested = true
                            break

            # Check for exposures too close together (check for overlapping
            # triggers already performed in self.trigger_device.trigger()):
            if not already_requested:
                if camera.frames: #might not be necessary
                    for otherFrame, other_shutter_duration in camera.frames.items():
                        self.checkRecoveryTime(videoFrame, shutter_duration, otherFrame, other_shutter_duration)

                self.trigger_device.trigger(i, shutter_duration)
                self.frames[i] = shutter_duration
                num_frames++

            self.videos.append(name, t, video_length, time_between_frames, shutter_duration, num_frames)
            else:
                video_length = 0
        return video_length #What is this used for??? how do we use this in other methods/classes?

    def expose(self, name, t, exposure_time=None):
        if exposure_time is None:
            shutter_duration = self.default_exposure
        else:
            shutter_duration = exposure_time

        if shutter_duration is None:
            raise LabscriptError('Camera %s has not had an exposure_time set as an instantiation argument, '%self.name +
                                 'and one was not specified for this exposure')
        if not shutter_duration > 0:
            raise LabscriptError("exposure_time must be > 0, not %s"%str(duration))

        # Only ask for a trigger if one has not already been requested by
        # another camera attached to the same trigger:
        already_requested = False
        for camera in self.trigger_device.child_devices:
            if camera is not self:
                if camera.frames.get(videoFrame) == duration:
                    already_requested = true
                    break

        # Check for exposures too close together (check for overlapping
        # triggers already performed in self.trigger_device.trigger()):
        if not already_requested:
            if camera.frames: #might not be necessary
                for otherFrame, other_shutter_duration in self.frames.items():
                    self.checkRecoveryTime(t, shutter_duration, otherFrame, other_shutter_duration)

            self.trigger_device.trigger(t, duration)
            self.frames[t] = shutter_duration

        # Check for exposures too close together (check for overlapping
        # triggers already performed in self.trigger_device.trigger()):

        self.exposures.append((name, t, duration))
        return duration

    def checkRecoveryTime(self, timeOne, durationOne, timeTwo, durationTwo):
        start = timeOne
        end = timeOne + durationOne

        other_start = timeTwo
        other_end = timeTwo + durationTwo

        if abs(other_start - end) < self.minimum_recovery_time or abs(other_end - start) < self.minimum_recovery_time:
            raise LabscriptError('%s %s has two exposures closer together than the minimum recovery time: ' %(self.description, self.name) + \
                                 'one at t = %fs for %fs, and another at t = %fs for %fs. '%(t,duration,start,duration) + \
                                 'The minimum recovery time is %fs.'%self.minimum_recovery_time)

    def generate_code(self, hdf5_file):
        self.do_checks()
        table_dtypes = [('name','a256'), ('time',float), ('exposure_time',float)]
        data = np.array(self.exposures,dtype=table_dtypes)

        group = self.init_device_group(hdf5_file)

        if self.exposures:
            group.create_dataset('EXPOSURES', data=data)

        table_dtypes = [('name','a256'), ('time',float), ('video_length',float), ('time_between_frames',float), ('exposure_time',float), ('number_of_frames',int)]
        data = np.array(self.videos, dtype=table_dtypes)
        if self.videos:
            group.create_dataset('VIDEOS', data=data)

        # DEPRECATED backward campatibility for use of exposuretime keyword argument instead of exposure_time:
        self.set_property('exposure_time', self.exposure_time, location='device_properties', overwrite=True)

    def do_checks(self):
        # Check that all Cameras sharing a trigger device have exposures when we have exposures:
        for frame, shutter_duration in self.frames.items():
            for camera in self.trigger_device.child_devices:
                if camera is not self:
                    if camera.frames: #might not be necessary
                        if camera.frames.get(otherFrame) != self.frames.get(frame):
                            raise LabscriptError('Cameras %s and %s share a trigger. ' % (self.name, camera.name) +
                                                 '%s has a video at %fs for %fs, ' % (self.name, start, other_video_length) +
                                                 'with %fs between frames and a shutter duration of %fs' %(other_time_between_frames, other_shutter_duration) +
                                                 'but there is no matching video for %s. ' % camera.name +
                                                 'Cameras sharing a trigger must have identical exposure times and durations.')

#For checkRecoveryTime calls, do we still take the photo and/or append it to the frames everytime even if it throws an error?
#Should self.videos.append(name, t, video_length, time_between_frames, shutter_duration) & self.exposures.append((name, t, frametype, duration)) be outside the if not already_requested: ???
#Can create a tuple array storing start/end times of frames to perform a binary search on for do_checks and checkRecoveryTime

@BLACS_tab
class PythonCameraTab(CameraTab):
    pass
