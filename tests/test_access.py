#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File   : test_optimisation.py
# License: GNU v3.0
# Author : Andrei Leonard Nicusan <a.l.nicusan@bham.ac.uk>
# Date   : 30.01.2022


import os
import sys
import textwrap

import coexist


def test_access_data():
    # Current, modern format
    data = coexist.AccessData.read("access_data/access_seed123")
    print(data)

    # Legacy coexist-0.1.0 format
    data = coexist.AccessData.read("access_data/access_info_000042")
    print(data)

    # Read data using direct class constructor
    coexist.AccessData("access_data/access_seed123")


def test_access():
    # Simple, idiomatic, correct test
    code = textwrap.dedent('''
        # ACCESS PARAMETERS START
        import sys
        import coexist

        parameters = coexist.create_parameters(
            ["fp1", "fp2", "fp3"],
            [-5, -5, -5],
            [10, 10, 10],
        )
        # ACCESS PARAMETERS END

        print("Example stdout message.")
        print("Example stderr message.", file=sys.stderr)

        values = parameters["value"]
        error = values["fp1"]**2 + values["fp2"]**2
    ''')

    file = "access_script1.py"
    with open(file, "w") as f:
        f.write(code)

    access = coexist.Access(file)
    print(access)

    data = access.learn(random_seed = 123)
    print(access)
    print(data)

    data = coexist.AccessData.read(access.paths.directory)
    print(data)

    # Weird parameters directives
    code = textwrap.dedent('''
        #####   ACCES \t PARAMETERS    START\tmama mia pizzeria
        import sys
        import coexist

        parameters = coexist.create_parameters(
            ["fp1", "fp2", "fp3"],
            [-5, -5, -5],
            [10, 10, 10],
        )
        ##   ACCESS   PARAMETERS   END

        print("Example stdout message.")
        print("Example stderr message.", file=sys.stderr)

        values = parameters["value"]
        error = values["fp1"]**2 + values["fp2"]**2 + values["fp3"]**4
    ''')

    file = "access_script2.py"
    with open(file, "w") as f:
        f.write(code)

    coexist.Access(file).learn(random_seed = 124)


def test_access_multi_objective():
    # Simple, idiomatic, correct multi-objective ACCES test
    code = textwrap.dedent('''
        # ACCESS PARAMETERS START
        import sys
        import coexist

        parameters = coexist.create_parameters(
            ["fp1", "fp2", "fp3"],
            [-5, -5, -5],
            [10, 10, 10],
        )
        # ACCESS PARAMETERS END

        print("Example stdout message.")
        print("Example stderr message.", file=sys.stderr)

        values = parameters["value"]
        error = [
            values["fp1"]**2 + values["fp2"]**2,
            values["fp1"]**2 * values["fp3"],
        ]
    ''')

    file = "access_script_multi1.py"
    with open(file, "w") as f:
        f.write(code)

    access = coexist.Access(file)
    print(access)

    data = access.learn(random_seed = 123)
    print(access)
    print(data)

    data = coexist.AccessData(access.paths.directory)
    print(data)

    # Multi-objective ACCES test where some jobs crash
    code = textwrap.dedent('''
        # ACCESS PARAMETERS START
        import sys
        import coexist

        parameters = coexist.create_parameters(
            ["fp1", "fp2", "fp3"],
            [-5, -5, -5],
            [10, 10, 10],
        )

        access_id = 0
        # ACCESS PARAMETERS END

        print("Example stdout message.")
        print("Example stderr message.", file=sys.stderr)

        # Make some simulations crash
        if access_id < 8:
            raise ValueError("Crashing first 8 epochs...")

        if access_id >= 8 and access_id < 10:
            raise ValueError("Crashing simulations 8 and 9...")

        values = parameters["value"]
        error = [
            values["fp1"]**2 + values["fp2"]**2,
            values["fp1"]**2 * values["fp3"],
        ]
    ''')

    file = "access_script_multi1.py"
    with open(file, "w") as f:
        f.write(code)

    access = coexist.Access(file)
    print(access)

    data = access.learn(num_solutions = 8, random_seed = 123)
    print(access)
    print(data)

    data = coexist.AccessData(access.paths.directory)
    print(data)


def test_multi_objective_combiners():
    # TODO: check the multi-objective classes work
    pass


def test_access_plots():
    # Using AccessData
    data = coexist.AccessData.read("access_data/access_seed123")
    coexist.plots.access(data)
    coexist.plots.access2d(data)

    # Using the filepaths only
    coexist.plots.access("access_data/access_seed123")
    coexist.plots.access2d("access_data/access_seed123")


def test_schedulers():
    s1 = coexist.schedulers.LocalScheduler()
    print(s1)
    assert s1.generate()[0] == sys.executable

    s2 = coexist.schedulers.SlurmScheduler(
        "10:0:0",
        commands = """
            # Commands to add in the sbatch script after `#`
            set -e
            module purge; module load bluebear
            module load BEAR-Python-DataScience
        """,
        qos = "bbdefault",
        account = "windowcr-rt-royalsociety",
        constraint = "cascadelake",
        mem_per_cpu = "4G",
    )
    print(s2)

    assert s2.generate()[0] == "sbatch"
    assert os.path.isfile("access_single_submission.sh")


if __name__ == "__main__":
    test_access_data()
    test_access()
    test_access_plots()
    test_schedulers()
