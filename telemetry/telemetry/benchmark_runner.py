# Copyright 2013 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Parses the command line, discovers the appropriate benchmarks, and runs them.

Handles benchmark configuration, but all the logic for
actually running the benchmark is in Benchmark and PageRunner."""

import hashlib
import inspect
import json
import os
import sys

from telemetry import benchmark
from telemetry import decorators
from telemetry.core import browser_finder
from telemetry.core import browser_options
from telemetry.core import command_line
from telemetry.core import discover
from telemetry.core import environment
from telemetry.core import util
from telemetry.util import find_dependencies


class Help(command_line.OptparseCommand):
  """Display help information about a command"""

  usage = '[command]'

  def Run(self, args):
    if len(args.positional_args) == 1:
      commands = _MatchingCommands(args.positional_args[0])
      if len(commands) == 1:
        command = commands[0]
        parser = command.CreateParser()
        command.AddCommandLineArgs(parser)
        parser.print_help()
        return 0

    print >> sys.stderr, ('usage: %s [command] [<options>]' % _ScriptName())
    print >> sys.stderr, 'Available commands are:'
    for command in _Commands():
      print >> sys.stderr, '  %-10s %s' % (
          command.Name(), command.Description())
    print >> sys.stderr, ('"%s help <command>" to see usage information '
                          'for a specific command.' % _ScriptName())
    return 0


class List(command_line.OptparseCommand):
  """Lists the available benchmarks"""

  usage = '[benchmark_name] [<options>]'

  @classmethod
  def CreateParser(cls):
    options = browser_options.BrowserFinderOptions()
    parser = options.CreateParser('%%prog %s %s' % (cls.Name(), cls.usage))
    return parser

  @classmethod
  def AddCommandLineArgs(cls, parser):
    parser.add_option('-j', '--json-output-file', type='string')
    parser.add_option('-n', '--num-shards', type='int', default=1)

  @classmethod
  def ProcessCommandLineArgs(cls, parser, args):
    if not args.positional_args:
      args.benchmarks = _Benchmarks()
    elif len(args.positional_args) == 1:
      args.benchmarks = _MatchBenchmarkName(args.positional_args[0],
                                            exact_matches=False)
    else:
      parser.error('Must provide at most one benchmark name.')

  def Run(self, args):
    possible_browser = browser_finder.FindBrowser(args)
    if args.browser_type in (
        'exact', 'release', 'release_x64', 'debug', 'debug_x64', 'canary'):
      args.browser_type = 'reference'
      possible_reference_browser = browser_finder.FindBrowser(args)
    else:
      possible_reference_browser = None
    if args.json_output_file:
      with open(args.json_output_file, 'w') as f:
        f.write(_GetJsonBenchmarkList(possible_browser,
                                      possible_reference_browser,
                                      args.benchmarks, args.num_shards))
    else:
      _PrintBenchmarkList(args.benchmarks, possible_browser)
    return 0


class Run(command_line.OptparseCommand):
  """Run one or more benchmarks (default)"""

  usage = 'benchmark_name [page_set] [<options>]'

  @classmethod
  def CreateParser(cls):
    options = browser_options.BrowserFinderOptions()
    parser = options.CreateParser('%%prog %s %s' % (cls.Name(), cls.usage))
    return parser

  @classmethod
  def AddCommandLineArgs(cls, parser):
    benchmark.AddCommandLineArgs(parser)

    # Allow benchmarks to add their own command line options.
    matching_benchmarks = []
    for arg in sys.argv[1:]:
      matching_benchmarks += _MatchBenchmarkName(arg)

    if matching_benchmarks:
      # TODO(dtu): After move to argparse, add command-line args for all
      # benchmarks to subparser. Using subparsers will avoid duplicate
      # arguments.
      matching_benchmark = matching_benchmarks.pop()
      matching_benchmark.AddCommandLineArgs(parser)
      # The benchmark's options override the defaults!
      matching_benchmark.SetArgumentDefaults(parser)

  @classmethod
  def ProcessCommandLineArgs(cls, parser, args):
    if not args.positional_args:
      possible_browser = (
          browser_finder.FindBrowser(args) if args.browser_type else None)
      _PrintBenchmarkList(_Benchmarks(), possible_browser)
      sys.exit(-1)

    input_benchmark_name = args.positional_args[0]
    matching_benchmarks = _MatchBenchmarkName(input_benchmark_name)
    if not matching_benchmarks:
      print >> sys.stderr, 'No benchmark named "%s".' % input_benchmark_name
      print >> sys.stderr
      _PrintBenchmarkList(_Benchmarks(), None)
      sys.exit(-1)

    if len(matching_benchmarks) > 1:
      print >> sys.stderr, ('Multiple benchmarks named "%s".' %
                            input_benchmark_name)
      print >> sys.stderr, 'Did you mean one of these?'
      print >> sys.stderr
      _PrintBenchmarkList(matching_benchmarks, None)
      sys.exit(-1)

    benchmark_class = matching_benchmarks.pop()
    if len(args.positional_args) > 1:
      parser.error('Too many arguments.')

    assert issubclass(benchmark_class, benchmark.Benchmark), (
        'Trying to run a non-Benchmark?!')

    benchmark.ProcessCommandLineArgs(parser, args)
    benchmark_class.ProcessCommandLineArgs(parser, args)

    cls._benchmark = benchmark_class

  def Run(self, args):
    return min(255, self._benchmark().Run(args))


def _ScriptName():
  return os.path.basename(sys.argv[0])


def _Commands():
  """Generates a list of all classes in this file that subclass Command."""
  for _, cls in inspect.getmembers(sys.modules[__name__]):
    if not inspect.isclass(cls):
      continue
    if not issubclass(cls, command_line.Command):
      continue
    yield cls

def _MatchingCommands(string):
  return [command for command in _Commands()
         if command.Name().startswith(string)]

@decorators.Cache
def _Benchmarks():
  benchmarks = []
  for base_dir in config.base_paths:
    benchmarks += discover.DiscoverClasses(base_dir, base_dir,
                                           benchmark.Benchmark,
                                           index_by_class_name=True).values()
  return benchmarks

def _MatchBenchmarkName(input_benchmark_name, exact_matches=True):
  def _Matches(input_string, search_string):
    if search_string.startswith(input_string):
      return True
    for part in search_string.split('.'):
      if part.startswith(input_string):
        return True
    return False

  # Exact matching.
  if exact_matches:
    # Don't add aliases to search dict, only allow exact matching for them.
    if input_benchmark_name in config.benchmark_aliases:
      exact_match = config.benchmark_aliases[input_benchmark_name]
    else:
      exact_match = input_benchmark_name

    for benchmark_class in _Benchmarks():
      if exact_match == benchmark_class.Name():
        return [benchmark_class]
    return []

  # Fuzzy matching.
  return [benchmark_class for benchmark_class in _Benchmarks()
          if _Matches(input_benchmark_name, benchmark_class.Name())]


def _GetJsonBenchmarkList(possible_browser, possible_reference_browser,
                          benchmark_classes, num_shards):
  """Returns a list of all enabled benchmarks in a JSON format expected by
  buildbots.

  JSON format (see build/android/pylib/perf/benchmark_runner.py):
  { "version": <int>,
    "steps": {
      <string>: {
        "device_affinity": <int>,
        "cmd": <string>,
        "perf_dashboard_id": <string>,
      },
      ...
    }
  }
  """
  output = {
    'version': 1,
    'steps': {
    }
  }
  for benchmark_class in benchmark_classes:
    if not issubclass(benchmark_class, benchmark.Benchmark):
      continue
    if not decorators.IsEnabled(benchmark_class, possible_browser):
      continue

    base_name = benchmark_class.Name()
    base_cmd = [sys.executable, os.path.realpath(sys.argv[0]),
                '-v', '--output-format=chartjson', '--upload-results',
                base_name]
    perf_dashboard_id = base_name
    # TODO(tonyg): Currently we set the device affinity to a stable hash of the
    # benchmark name. This somewhat evenly distributes benchmarks among the
    # requested number of shards. However, it is far from optimal in terms of
    # cycle time.  We should add a benchmark size decorator (e.g. small, medium,
    # large) and let that inform sharding.
    device_affinity = int(hashlib.sha1(base_name).hexdigest(), 16) % num_shards

    output['steps'][base_name] = {
      'cmd': ' '.join(base_cmd + [
            '--browser=%s' % possible_browser.browser_type]),
      'device_affinity': device_affinity,
      'perf_dashboard_id': perf_dashboard_id,
    }
    if (possible_reference_browser and
        decorators.IsEnabled(benchmark_class, possible_reference_browser)):
      output['steps'][base_name + '.reference'] = {
        'cmd': ' '.join(base_cmd + [
              '--browser=reference', '--output-trace-tag=_ref']),
        'device_affinity': device_affinity,
        'perf_dashboard_id': perf_dashboard_id,
      }

  return json.dumps(output, indent=2, sort_keys=True)


def _PrintBenchmarkList(benchmarks, possible_browser):
  if not benchmarks:
    print >> sys.stderr, 'No benchmarks found!'
    return

  # Align the benchmark names to the longest one.
  format_string = '  %%-%ds %%s' % max(len(b.Name()) for b in benchmarks)

  filtered_benchmarks = [benchmark_class for benchmark_class in benchmarks
                         if issubclass(benchmark_class, benchmark.Benchmark)]
  disabled_benchmarks = []
  if filtered_benchmarks:
    print >> sys.stderr, 'Available benchmarks %sare:' % (
        'for %s ' %possible_browser.browser_type if possible_browser else '')
    for benchmark_class in sorted(filtered_benchmarks, key=lambda b: b.Name()):
      if possible_browser and not decorators.IsEnabled(benchmark_class,
                                                       possible_browser):
        disabled_benchmarks.append(benchmark_class)
        continue
      print >> sys.stderr, format_string % (
          benchmark_class.Name(), benchmark_class.Description())

    if disabled_benchmarks:
      print >> sys.stderr, (
          'Disabled benchmarks for %s are (force run with -d): ' %
          possible_browser.browser_type)
      for benchmark_class in disabled_benchmarks:
        print >> sys.stderr, format_string % (
            benchmark_class.Name(), benchmark_class.Description())
    print >> sys.stderr, (
        'Pass --browser to list benchmarks for another browser.')
    print >> sys.stderr


config = environment.Environment([util.GetBaseDir()])


def main():
  # Get the command name from the command line.
  if len(sys.argv) > 1 and sys.argv[1] == '--help':
    sys.argv[1] = 'help'

  command_name = 'run'
  for arg in sys.argv[1:]:
    if not arg.startswith('-'):
      command_name = arg
      break

  # Validate and interpret the command name.
  commands = _MatchingCommands(command_name)
  if len(commands) > 1:
    print >> sys.stderr, ('"%s" is not a %s command. Did you mean one of these?'
                          % (command_name, _ScriptName()))
    for command in commands:
      print >> sys.stderr, '  %-10s %s' % (
          command.Name(), command.Description())
    return 1
  if commands:
    command = commands[0]
  else:
    command = Run

  # Parse and run the command.
  parser = command.CreateParser()
  command.AddCommandLineArgs(parser)
  options, args = parser.parse_args()
  if commands:
    args = args[1:]
  options.positional_args = args
  command.ProcessCommandLineArgs(parser, options)
  return command().Run(options)
