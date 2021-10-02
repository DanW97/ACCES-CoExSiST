#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File   : utilities.py
# License: GNU v3.0
# Author : Andrei Leonard Nicusan <a.l.nicusan@bham.ac.uk>
# Date   : 04.08.2021


import  os
import  re
import  pickle
from    textwrap    import  indent

import  numpy       as      np
import  pandas      as      pd
import  attr




@attr.s(auto_attribs = True, frozen = True, slots = True, repr = False)
class AccessData:
    '''Access (pun intended) data generated by a ``coexist.Access`` run; read
    it in using ``coexist.AccessData.read("access_info_<hashcode>")``.

    Examples
    --------
    Suppose you run ``coexist.Access.learn(random_seed = 12345)`` - then a
    directory "access_info_012345/" would be generated. Access (yes, still
    intended) all data generated in a Python-friendly format using:

    >>> import coexist
    >>> data = coexist.AccessData.read("access_info_012345")
    >>> data
    AccessData(
      parameters:
                    value  min  max  sigma
        cor           1.0 -3.0  5.0    3.2
        separation    2.0 -7.0  3.0    4.0
      num_solutions:
        10
      target_sigma:
        0.1
      random_seed:
        12345
      results:
                  cor  separation   cor_std  separation_std  overall_std         error
        0   -2.951101   -0.355040  2.924122        2.937551     0.909126   8231.293330
        1   -1.786118    0.963281  2.924122        2.937551     0.909126    503.686312
        2    0.758901   -0.963613  2.924122        2.937551     0.909126    237.077720
        3   -2.996387    2.104364  2.924122        2.937551     0.909126   4741.116426
        4    2.155386   -5.811648  2.924122        2.937551     0.909126  10936.922925
        ..        ...         ...       ...             ...          ...           ...
        245  1.008255    1.007301  0.045171        0.091158     0.074921      0.008676
        246  0.949818    0.887960  0.045171        0.091158     0.074921      0.022665
        247  1.030829    1.071152  0.045171        0.091158     0.074921      0.008248
        248  1.096043    1.221212  0.045171        0.091158     0.074921      0.048831
        249  0.953040    0.905585  0.045171        0.091158     0.074921      0.002935
        [250 rows x 6 columns]
      results_scaled:
                  cor  separation   cor_std  separation_std  overall_std         error
        0   -0.922219   -0.088760  0.913788        0.734388     0.909126   8231.293330
        1   -0.558162    0.240820  0.913788        0.734388     0.909126    503.686312
        2    0.237157   -0.240903  0.913788        0.734388     0.909126    237.077720
        3   -0.936371    0.526091  0.913788        0.734388     0.909126   4741.116426
        4    0.673558   -1.452912  0.913788        0.734388     0.909126  10936.922925
        ..        ...         ...       ...             ...          ...           ...
        245  0.315080    0.251825  0.014116        0.022789     0.074921      0.008676
        246  0.296818    0.221990  0.014116        0.022789     0.074921      0.022665
        247  0.322134    0.267788  0.014116        0.022789     0.074921      0.008248
        248  0.342514    0.305303  0.014116        0.022789     0.074921      0.048831
        249  0.297825    0.226396  0.014116        0.022789     0.074921      0.002935
        [250 rows x 6 columns]
      num_epochs:
        25
    )

    If you have a single *ACCES* run in a directory, you can you that name and
    ``coexist.AccessData.read`` will search it:

    >>> coexist.AccessData.read("parent_directory")

    Or, if you are executing the command within a directory that already has an
    `access_info_<hash_code>` folder, you can use the default ".":

    >>> coexist.AccessData.read()

    '''

    parameters: pd.DataFrame
    num_solutions: int
    target_sigma: float
    random_seed: int
    results: pd.DataFrame
    results_scaled: pd.DataFrame
    num_epochs: int


    @staticmethod
    def read(access_path = "."):
        '''Read in data generated by ``coexist.Access``; the `access_path` can
        be either the "`access_info_<hash>`" directory itself, or its
        parent directory.
        '''
        access_path = find_access_path(access_path)
        history_finder = re.compile(r"opt_history_[0-9]+\.csv")

        for f in os.listdir(access_path):
            if history_finder.search(f):
                history_path = os.path.join(access_path, f)
                history_scaled_path = (
                    history_path.split(".csv")[0] + "_scaled.csv"
                )
                num_solutions = int(
                    re.split(r"opt_history_|\.csv", history_path)[1]
                )

        with open(os.path.join(access_path, "access_info.pickle"), "rb") as f:
            access_info = pickle.load(f)

        history = np.loadtxt(history_path)
        history_scaled = np.loadtxt(history_scaled_path)

        results_columns = list(access_info.parameters.index)
        results_columns += [rc + "_std" for rc in results_columns]
        results_columns += ["overall_std", "error"]

        results = pd.DataFrame(
            data = history,
            columns = results_columns,
            dtype = float,
        )

        results_scaled = pd.DataFrame(
            data = history_scaled,
            columns = results_columns,
            dtype = float,
        )

        data = AccessData(
            access_info.parameters,
            num_solutions,
            access_info.target_sigma,
            access_info.random_seed,
            results,
            results_scaled,
            len(history) // num_solutions,
        )

        return data


    def __str__(self):
        return "\n".join((
            f"{s}:\n{indent(str(getattr(self, s)), '  ')}\n"
            for s in self.__slots__ if not s.startswith("_")
        ))


    def __repr__(self):
        return "AccessData(\n" + indent(self.__str__(), "  ") + ")"




def find_access_path(path):
    '''Find the `access_info_<hash>` directory given an input `path`, either:

    1. The `access_info_<hash>` directory itself, simple.
    2. The parent directory.
    '''

    if path.startswith("access_info_"):
        return path

    for f in os.listdir(path):
        if f.startswith("access_info_"):
            return os.path.join(path, f)

    # If no `access_info_<hash>` was found, return the path as is
    return path