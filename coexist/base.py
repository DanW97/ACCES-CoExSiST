#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File   : pyLiggghts.py
# License: GNU v3.0
# Author : Andrei Leonard Nicusan <a.l.nicusan@bham.ac.uk>
# Date   : 01.09.2020


import io
import re
import os
import sys
import signal
import textwrap
import tempfile
import platform

import ctypes
from contextlib import contextmanager

import numpy as np
import pandas as pd

from liggghts import liggghts



class Parameters(pd.DataFrame):
    '''Pandas DataFrame subclass with a custom constructor for LIGGGHTS
    simulation parameters.

    In order to dynamically change LIGGGHTS simulation parameters, a macro
    command must be run (e.g. `liggghts.command(fix  m1 all property/global
    youngsModulus peratomtype 0.8e9)`). This class saves the data needed to
    modify simulation parameters in a DataFrame:

        1. The required *command template* to change a given parameter using
           LIGGGHTS equal-style variables. E.g. "fix  m1 all property/global
           youngsModulus peratomtype ${youngmodP} ${youngmodP} ${youngmodP}" is
           a LIGGGHTS command which uses the ${youngmodP} variable.

        2. Per-parameter initial guesses.

        3. Per-parameter lower bounds (i.e. minimum valid value), optional.

        4. Per-parameter upper bounds (i.e. maximum valid value), optional.

    All those values are indexed by the parameter name. Below is an example
    that shows how to construct a `Parameters` class containing a hypothetical
    simulation's properties that will be dynamically changed.

    Examples
    --------
    In the example below, the command to change a single simulation parameter
    contains other variables which we won't modify:

    >>> parameters = Parameters(
    >>>     ["corPP", "youngmodP"],
    >>>     ["fix  m3 all property/global coefficientRestitution \
    >>>         peratomtypepair 3 ${corPP} ${corPW} ${corPW2} \
    >>>                                    ${corPW} ${corPW2} ${corPW} \
    >>>                                    ${corPW2} ${corPW} ${corPW} ",
    >>>      "fix  m1 all property/global youngsModulus peratomtype \
    >>>         ${youngmodP} ${youngmodP} ${youngmodP}"],
    >>>     [0.5, 0.8e9],
    >>>     [0.0, None],
    >>>     [1.0, None],
    >>> )
    >>>
    >>> parameters
    >>>                                              command  value   min  max
    >>> corPP  fix  m3 all property/global coefficientRes...    0.5  None  0.0
    >>> corPW  fix  m3 all property/global coefficientRes...    0.5  None  1.0

    Notes
    -----
    As this class inherits from `pandas.DataFrame`, all methods from it are
    available after instantiation - only the constructor is custom.
    '''

    def __init__(
        self,
        variables,
        commands,
        initial_values,
        minimums,
        maximums,
        sigma0 = None,
    ):
        '''`Parameters` class constructor.

        Parameters
        ----------
        variables: list[str]
            An iterable containing the LIGGGHTS variable names that will be
            used for changing simulation parameters.

        commands: list[str]
            An iterable containing the macro commands required to modify
            LIGGGHTS simulation parameters, containing the variable names
            as `${varname}`. E.g. `"fix  m1 all property/global youngsModulus
            peratomtype ${youngmodP} ${youngmodP} ${youngmodP}"`.

        initial_values: list[float]
            An iterable containing the initial values for each LIGGGHTS
            simulation parameter.

        minimums: list[float]
            An iterable containing the lower bounds for each LIGGGHTS
            parameter. For non-existing bounds, use `None`, in which case also
            define a `sigma0`.

        maximums: list[float]
            An iterable containing the upper bounds for each LIGGGHTS
            parameter. For non-existing bounds, use `None`, in which case also
            define a `sigma0`.

        sigma0: list[float], optional
            The standard deviation of the first population of solutions tried
            by the CMA-ES optimisation algorithm. If unset, it is computed as
            `0.2 * (maximum - minimum)`.
        '''

        if not (len(variables) == len(commands) == len(initial_values) ==
                len(minimums) == len(maximums)):
            raise ValueError(textwrap.fill(
                '''The input iterables `variables`, `commands`,
                `initial_values`, `minimums` and `maximums` must all have the
                same length.'''
            ))

        initial_values = np.array(initial_values, dtype = float)
        minimums = np.array(minimums, dtype = float)
        maximums = np.array(maximums, dtype = float)

        if (minimums >= maximums).any():
            raise ValueError(textwrap.fill(
                '''Found value in `maximums` that was smaller or equal than the
                corresponding value in `minimums`.'''
            ))

        if sigma0 is None:
            sigma0 = 0.2 * (maximums - minimums)
        elif len(sigma0) != len(variables):
            raise ValueError(textwrap.fill(
                '''If defined, `sigma0` must have the same length as the other
                input parameters.'''
            ))

        for cmd in commands:
            if re.search("\$\{\w+\}", cmd) is None:
                raise ValueError(textwrap.fill(
                    '''The strings in the input `commands` must contain at
                    least one substring `"${varname}"` (e.g. `"fix  m2 all
                    property/global poissonsRatio peratomtype ${poissP}
                    ${poissP} ${poissP}"`), in which the right value will be
                    substituted when running the LIGGGHTS command.'''
                ))

        parameters = {
            "command": commands,
            "value": initial_values,
            "min": minimums,
            "max": maximums,
            "sigma": sigma0,
        }

        pd.DataFrame.__init__(self, parameters, index = variables)




class Simulation:
    '''Class encapsulating a single LIGGGHTS simulation whose parameters will
    be modified dynamically by a driver code.

    '''

    def __init__(
        self,
        simulation,
        parameters,
        verbose = True
    ):
        '''`Simulation` class constructor.

        Parameters
        ----------
        simulation: path-like object or str
            LIGGGHTS macro script for setting up a simulation - either a path
            (relative or absolute, e.g. "../in.sim") or a `str` containing the
            actual macro commands.

        parameters: Parameters instance
            The LIGGGHTS simulation parameters that will be dynamically
            modified, encapsulated in a `Parameters` class instance. Check its
            documentation for further information and example instantiation.

        verbose: bool, default `True`
            Show LIGGGHTS output while simulation is running.
        '''

        self._verbose = bool(verbose)
        self._log = io.BytesIO()

        if self._verbose:
            self.simulation = liggghts()
        else:
            self.simulation = liggghts(cmdargs = ["-screen", "/dev/null"])

        with open(simulation) as f:
            self.simulation.file(simulation)
            self.filename = simulation

        if not isinstance(parameters, Parameters):
            raise TypeError(textwrap.fill(
                f'''The input `parameters` must be an instance of the
                `Parameters` class. Received {type(parameters)}.'''
            ))

        self.parameters = parameters
        self._step_size = self.simulation.extract_global("dt", 1)

        # Set simulation parameters to the values in `parameters`
        for idx in self.parameters.index:
            self[idx] = self.parameters.loc[idx, "value"]


    @property
    def step_size(self):
        # save a step_size property of the class, so we can define the
        # step_size
        return self._step_size


    @step_size.setter
    def step_size(self, new_step_size):
        # set the step_size size
        if 0 < new_step_size < 1:
            self._step_size = new_step_size
            self.simulation.command(f"timestep {new_step_size}")
        else:
            raise ValueError("Step size must be between 0 and 1 !")


    @property
    def verbose(self):
        self._verbose


    @verbose.setter
    def verbose(self, verbose):
        self._verbose = bool(verbose)


    def save(self, filename = "restart.data"):
        # write a restart file
        cmd = f"write_restart {filename}"
        self.simulation.command(cmd)


    def load(self, filename = "restart.data"):
        # load a new simulation based on the position data from filename and
        # the system based on self.filename
        #
        # 1st:
        # open the simulation file and search for the line where it reads the
        # restart then change the filename in this file and save
        with open(self.filename, "r") as f:
            lines = f.readlines()

        for i, line in enumerate(lines):
            if line.split("read_restart")[0] == "":
                lines[i] = f"read_restart {filename}\n"

        temporary_fname = f"temp_{int(np.random.random() * 1000000)}.restart"
        with open(temporary_fname, "w+") as f:
            f.writelines(lines)

        # 2nd:
        # close current simulation and open new one
        self.simulation.close()

        if self._verbose:
            self.simulation = liggghts()
        else:
            self.simulation = liggghts(cmdargs = ["-screen", "/dev/null"])

        self.simulation.file(temporary_fname)
        os.remove(temporary_fname)


    def num_atoms(self):
        return self.simulation.get_natoms()


    def positions(self):
        # get particle positions
        pos = self.simulation.gather_atoms("x", 1, 3)
        pos = np.array(list(pos)).reshape(self.num_atoms(), -1)
        return pos


    def velocities(self):
        # get particle velocities
        vel = self.simulation.gather_atoms("v", 1, 3)
        vel = np.array(list(vel)).reshape(self.num_atoms(), -1)
        return vel


    def variable(self, var_name):
        return self.simulation.extract_variable(var_name, "", 0)


    def step(self, num_steps):
        # run simulation for `num_steps` timesteps
        if self.verbose:
            self.simulation.command(f"run {num_steps}")
        else:
            self.simulation.command(f"run {num_steps} post no")


    def step_to(self, timestamp):
        # run simulation up to timestep = `timestamp`
        if timestamp < self.timestep():
            raise ValueError(textwrap.fill(
                '''Timestep is below the current timestep.\nCheck input or
                reset the timestep!'''
            ))

        if self.verbose:
            self.simulation.command(f"run {timestamp} upto")
        else:
            self.simulation.command(f"run {timestamp} upto post no")


    def step_time(self, time):
        # find timestep which can run exectly to time
        # while beeing lower then self.step_size
        new_dt = time / (int(time / self.step_size) + 1)
        steps = time / new_dt

        old_dt = self.step_size
        self.step_size = new_dt
        self.step(steps)
        self.step_size = old_dt


    def step_to_time(self, time):
        # run simulation up to sim time = `time`
        if time < self.time():
            raise ValueError(textwrap.fill(
                '''Time is below the current simulation time. Check input or
                reset the timestep!'''
            ))

        rest_time = (time - self.time()) % self.step_size
        n_steps = (time - self.time()-rest_time) / self.step_size

        self.step(nsteps)

        # Now run 1 single timestep with a smaller timestep
        old_dt = self.step_size

        # set step size to the rest time
        self.step_size = rest_time
        self.step(1)

        # reset to normal dt
        self.step_size = old_dt


    def reset_time(self):
        # reset the current timestep to 0
        self.simulation.command("reset_timestep 0")


    def timestep(self):
        # return the current timestep
        return self.simulation.extract_global("ntimestep", 0)


    def time(self):
        return self.simulation.extract_global("atime", 1)


    def __setitem__(self, key, value):
        # Custom key-value setter to change a parameter in the class *and*
        # during the simulation.
        # Raises an AttributeError if the key didn't exist previously.
        if not key in self.parameters.index:
            raise AttributeError(textwrap.fill(
                f'''The given parameter name (the `key`) does not exist. It
                should be set when instantiating the `Parameters`. Received
                {key}.'''
            ))

        # Extracts variable LIGGGHTS substitutions, like ${corPP} => corPP
        variable_extractor = re.compile("\$\{|\}")

        # Substitute all occurences of ${varname} in the LIGGGHTS command with:
        #   1. `value` if `varname` == `key`
        #   2. the LIGGGHTS variable `varname` otherwise
        def replace_var(match):
            var = variable_extractor.split(match.group(0))[1]

            if var == key:
                return str(value)
            else:
                return str(self.variable(var))

        cmd = re.sub(
            "\$\{\w+\}",
            replace_var,
            self.parameters.loc[key, "command"]
        )

        # Run the command with replaced varnames
        self.simulation.command(cmd)

        # Modify the global variable name to reflect the change
        self.simulation.command(f"variable {key} equal {value}")

        # Set inner class parameter value
        self.parameters.at[key, "value"] = value


    def __del__(self):
        self.simulation.close()


    def __str__(self):
        # Shown when calling print(class)
        docstr = (
            f"simulation:\n{self.simulation}\n\n"
            f"parameters:\n{self.parameters}"
        )

        return docstr


    def __repr__(self):
        # Shown when writing the class on a REPL

        docstr = (
            "Class instance that inherits from `pyLiggghts.Simulation`.\n"
            f"Type:\n{type(self)}\n\n"
            "Attributes\n----------\n"
            f"{self.__str__()}"
        )

        return docstr




if __name__ == "main":
    parameters = Parameters(
        ["corPP", "corPW"],
        ["fix  m3 all property/global coefficientRestitution peratomtypepair 3 \
            ${corPP} ${corPW} ${corPW2} \
            ${corPW} ${corPW2} ${corPW} \
            ${corPW2} ${corPW} ${corPW} ",
        "fix  m3 all property/global coefficientRestitution peratomtypepair 3 \
            ${corPP} ${corPW} ${corPW2} \
            ${corPW} ${corPW2} ${corPW} \
            ${corPW2} ${corPW} ${corPW} "],
        [0.5, 0.5],     # Initial values
        [0.0, 0.0],     # Minimum values
        [1.0, 1.0]      # Maximum values
    )

    simulation = Simulation("run.sim", parameters)

    simulation.save()
    simulation.step(200)

    simulation.save("2.save")
    simulation.step(200)

    simulation.load("2.save")

    simulation.step(200)


    print("\nInitial simulation parameters:")
    print(f"corPP: {simulation.variable('corPP')}")
    print(f"corPW: {simulation.variable('corPW')}")

    simulation["corPP"] = 0.75
    simulation["corPW"] = 0.25

    print("\nModified simulation parameters:")
    print(f"corPP: {simulation.variable('corPP')}")
    print(f"corPW: {simulation.variable('corPW')}")




