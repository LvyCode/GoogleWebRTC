# Copyright 2013 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import weakref

from telemetry.core.platform import network_controller_backend
from telemetry.core.platform import profiling_controller_backend
from telemetry.core.platform import tracing_controller_backend


# pylint: disable=W0613

# pylint: disable=W0212
class OSVersion(str):
  def __new__(cls, friendly_name, sortable_name, *args, **kwargs):
    version = str.__new__(cls, friendly_name)
    version._sortable_name = sortable_name
    return version

  def __lt__(self, other):
    return self._sortable_name < other._sortable_name

  def __gt__(self, other):
    return self._sortable_name > other._sortable_name

  def __le__(self, other):
    return self._sortable_name <= other._sortable_name

  def __ge__(self, other):
    return self._sortable_name >= other._sortable_name


XP = OSVersion('xp', 5.1)
VISTA = OSVersion('vista', 6.0)
WIN7 = OSVersion('win7', 6.1)
WIN8 = OSVersion('win8', 6.2)

LEOPARD = OSVersion('leopard', 105)
SNOWLEOPARD = OSVersion('snowleopard', 106)
LION = OSVersion('lion', 107)
MOUNTAINLION = OSVersion('mountainlion', 108)
MAVERICKS = OSVersion('mavericks', 109)
YOSEMITE = OSVersion('yosemite', 1010)


class PlatformBackend(object):

  def __init__(self, device=None):
    """ Initalize an instance of PlatformBackend from a device optionally.
      Call sites need to use SupportsDevice before intialization to check
      whether this platform backend supports the device.
      If device is None, this constructor returns the host platform backend
      which telemetry is running on.

      Args:
        device: an instance of telemetry.core.platform.device.Device.
    """
    if device and not self.SupportsDevice(device):
      raise ValueError('Unsupported device: %s' % device.name)
    self._platform = None
    self._running_browser_backends = weakref.WeakSet()
    self._network_controller_backend = (
        network_controller_backend.NetworkControllerBackend(self))
    self._tracing_controller_backend = (
        tracing_controller_backend.TracingControllerBackend(self))
    self._profiling_controller_backend = (
        profiling_controller_backend.ProfilingControllerBackend(self))

  @classmethod
  def SupportsDevice(cls, device):
    """ Returns whether this platform backend supports intialization from the
    device. """
    return False

  def SetPlatform(self, platform):
    assert self._platform == None
    self._platform = platform

  @property
  def platform(self):
    return self._platform

  @property
  def is_host_platform(self):
    return self._platform.is_host_platform

  @property
  def running_browser_backends(self):
    return list(self._running_browser_backends)

  @property
  def network_controller_backend(self):
    return self._network_controller_backend

  @property
  def tracing_controller_backend(self):
    return self._tracing_controller_backend

  @property
  def profiling_controller_backend(self):
    return self._profiling_controller_backend

  def DidCreateBrowser(self, browser, browser_backend):
    self.SetFullPerformanceModeEnabled(True)

    # TODO(slamm): Remove this call when replay browser_backend dependencies
    # get moved to platform. https://crbug.com/423962
    self._network_controller_backend.UpdateReplay(browser_backend)

  def DidStartBrowser(self, browser, browser_backend):
    assert browser not in self._running_browser_backends
    self._running_browser_backends.add(browser_backend)
    self._tracing_controller_backend.DidStartBrowser(
        browser, browser_backend)

  def WillCloseBrowser(self, browser, browser_backend):
    self._tracing_controller_backend.WillCloseBrowser(
        browser, browser_backend)
    self._profiling_controller_backend.WillCloseBrowser(
        browser_backend)
    # TODO(slamm): Move this call when replay's life cycle is no longer
    # tied to the browser. https://crbug.com/424777
    self._network_controller_backend.StopReplay()

    is_last_browser = len(self._running_browser_backends) <= 1
    if is_last_browser:
      self.SetFullPerformanceModeEnabled(False)

    self._running_browser_backends.discard(browser_backend)

  def GetBackendForBrowser(self, browser):
    matches = [x for x in self._running_browser_backends
               if x.browser == browser]
    if len(matches) == 0:
      raise Exception('No browser found')
    assert len(matches) == 1
    return matches[0]

  @property
  def wpr_http_device_port(self):
    return self._network_controller_backend.wpr_http_device_port

  @property
  def wpr_https_device_port(self):
    return self._network_controller_backend.wpr_https_device_port

  def IsRawDisplayFrameRateSupported(self):
    return False

  def StartRawDisplayFrameRateMeasurement(self):
    raise NotImplementedError()

  def StopRawDisplayFrameRateMeasurement(self):
    raise NotImplementedError()

  def GetRawDisplayFrameRateMeasurements(self):
    raise NotImplementedError()

  def SetFullPerformanceModeEnabled(self, enabled):
    pass

  def CanMonitorThermalThrottling(self):
    return False

  def IsThermallyThrottled(self):
    raise NotImplementedError()

  def HasBeenThermallyThrottled(self):
    raise NotImplementedError()

  def GetSystemCommitCharge(self):
    raise NotImplementedError()

  def GetSystemTotalPhysicalMemory(self):
    raise NotImplementedError()

  def GetCpuStats(self, pid):
    return {}

  def GetCpuTimestamp(self):
    return {}

  def PurgeUnpinnedMemory(self):
    pass

  def GetMemoryStats(self, pid):
    return {}

  def GetChildPids(self, pid):
    raise NotImplementedError()

  def GetCommandLine(self, pid):
    raise NotImplementedError()

  def GetArchName(self):
    raise NotImplementedError()

  def GetOSName(self):
    raise NotImplementedError()

  def GetOSVersionName(self):
    raise NotImplementedError()

  def CanFlushIndividualFilesFromSystemCache(self):
    raise NotImplementedError()

  def FlushEntireSystemCache(self):
    raise NotImplementedError()

  def FlushSystemCacheForDirectory(self, directory, ignoring=None):
    raise NotImplementedError()

  def FlushDnsCache(self):
    pass

  def LaunchApplication(
      self, application, parameters=None, elevate_privilege=False):
    raise NotImplementedError()

  def IsApplicationRunning(self, application):
    raise NotImplementedError()

  def CanLaunchApplication(self, application):
    return False

  def InstallApplication(self, application):
    raise NotImplementedError()

  def CanCaptureVideo(self):
    return False

  def StartVideoCapture(self, min_bitrate_mbps):
    raise NotImplementedError()

  @property
  def is_video_capture_running(self):
    return False

  def StopVideoCapture(self):
    raise NotImplementedError()

  def CanMonitorPower(self):
    return False

  def CanMeasurePerApplicationPower(self):
    return False

  def StartMonitoringPower(self, browser):
    raise NotImplementedError()

  def StopMonitoringPower(self):
    raise NotImplementedError()

  def ReadMsr(self, msr_number, start=0, length=64):
    """Read a CPU model-specific register (MSR).

    Which MSRs are available depends on the CPU model.
    On systems with multiple CPUs, this function may run on any CPU.

    Args:
      msr_number: The number of the register to read.
      start: The least significant bit to read, zero-indexed.
          (Said another way, the number of bits to right-shift the MSR value.)
      length: The number of bits to read. MSRs are 64 bits, even on 32-bit CPUs.
    """
    raise NotImplementedError()

  @property
  def wpr_ca_cert_path(self):
    return None

  def IsCooperativeShutdownSupported(self):
    """Indicates whether CooperativelyShutdown, below, is supported.
    It is not necessary to implement it on all platforms."""
    return False

  def CooperativelyShutdown(self, proc, app_name):
    """Cooperatively shut down the given process from subprocess.Popen.

    Currently this is only implemented on Windows. See
    crbug.com/424024 for background on why it was added.

    Args:
      proc: a process object returned from subprocess.Popen.
      app_name: on Windows, is the prefix of the application's window
          class name that should be searched for. This helps ensure
          that only the application's windows are closed.

    Returns True if it is believed the attempt succeeded.
    """
    raise NotImplementedError()
