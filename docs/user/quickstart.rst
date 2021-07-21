.. _peripy_docs_user_quickstart:

**********
Quickstart
**********

Examples
--------
You can find an examples of how to use the package under:examples/.
Run the first example by typing python examples/example1/example.py

The Model class
---------------
The :class:`peripy.model.Model` class allows users to define a bond-based
peridynamics model for composite materials with non-linear micromodulus
functions, stiffness correction factors and boundary conditions. The model
is defined by parameters and a set of initial conditions (coordinates,
connectivity and optionally bond_types and stiffness_corrections). For this an
:class:`peripy.integrators.Integrator` is required, and optionally
functions implementing the boundarys.

The Integrator class
--------------------

The :class:`peripy.integrators.Integrator` is the explicit time
integration method, see :mod:`peripy.integrators` for options.
Any integrator with the suffix 'CL' uses OpenCL kernels to calculate the
bond force and displacement update, resulting in orders of magnitude faster
simulation time when compared to using the cython implementation,
:class:`peripy.integrators.Euler`. OpenCL is 'heterogeneous' which
means the 'CL' integrator classes will work on a CPU device as well as a
GPU device. The preferable (faster) CL device will be chosen automatically.

    >>> from peridynamics import Model
    >>> from  peripy.integrators import EulerCL
    >>>
    >>> def is_displacement_boundary(x):
    >>>     # Node does not live on a boundary
    >>>     bnd = [None, None, None]
    >>>     # Node does live on a boundary
    >>>     if x[0] < 1.5 * 0.1:
    >>>         # These displacement boundary conditions
    >>>         # are applied in the negative x direction
    >>>         bnd[0] = -1
    >>>     elif x[0] > 1.0 - 1.5 * 0.1:
    >>>         # These displacement boundary conditions
    >>>         # are applied in the positive x direction
    >>>         bnd[0] = 1
    >>>     return bnd
    >>>
    >>> # for the cython implementation, use euler = Euler(dt)
    >>> euler = EulerCL(dt=1e-3)
    >>>
    >>> model = Model(
    >>>     mesh_file,
    >>>     integrator=euler,
    >>>     horizon=0.1,
    >>>     critical_stretch=0.005,
    >>>     bond_stiffness=18.00 * 0.05 / (np.pi * 0.1**4),
    >>>     is_displacement_boundary=is_displacement_boundary,
    >>>     )

Defining a crack
----------------

To define a crack in the inital configuration, you may supply a list of
pairs of nodes between which the crack is.

    >>> initial_crack = [(1,2), (5,7), (3,9)]
    >>> model = Model(
    >>>     mesh_file,
    >>>     integrator=euler,
    >>>     horizon=0.1,
    >>>     critical_stretch=0.005,
    >>>     bond_stiffness=18.00 * 0.05 / (np.pi * 0.1**4),
    >>>     is_displacement_boundary=is_displacement_boundary,
    >>>     initial_crack=initial_crack
    >>>     )

If it is more convenient to define the crack as a function you may also
pass a function to the constructor which takes the array of coordinates as
its only argument and returns a list of tuples as described above. The
:func:`peripy.model.initial_crack_helper` decorator has been provided
to easily create a function of the correct form from one which tests a
single pair of node coordinates and returns `True` or `False`.

    >>> from peridynamics import initial_crack_helper
    >>>
    >>> @initial_crack_helper
    >>> def initial_crack(x, y):
    >>>     ...
    >>>     if crack:
    >>>         return True
    >>>     else:
    >>>         return False
    >>>
    >>> model = Model(
    >>>     mesh_file,
    >>>     integrator=euler,
    >>>     horizon=0.1,
    >>>     critical_stretch=0.005,
    >>>     bond_stiffness=18.00 * 0.05 / (np.pi * 0.1**4),
    >>>     is_displacement_boundary=is_displacement_boundary,
    >>>     initial_crack=initial_crack
    >>>     )

Conducting a simulation
-----------------------

The :meth:`peripy.model.Model.simulate` method can be used to conduct a
peridynamics simulation. Here it is possible to define the boundary condition
magnitude throughout the simulation.

    >>> model = Model(...)
    >>>
    >>> # Number of time-steps
    >>> steps = 1000
    >>>
    >>> # Boundary condition magnitude throughout the simulation
    >>> displacement_bc_array = np.linspace(2.5e-6, 2.5e-3, steps)
    >>>
    >>> (u,
    >>>  ud,
    >>>  udd,
    >>>  force,
    >>>  body_force,
    >>>  damage,
    >>>  nlist,
    >>>  n_neigh) = model.simulate(
    >>>     steps=steps,
    >>>     displacement_bc_magnitudes=displacement_bc_array,
    >>>     write=100
    >>>     )

Conducting a simulation with initial conditions
-----------------------------------------------

It is possible to define initial conditions such as the
displacement vector `u`, the velocity vector `ud` and the
`connectivity` which is a `tuple`, (`nlist`, `n_neigh`). In
this example the first 1000 steps have been simulated,
generating the initial conditions for the next 1000 steps.
The first step has been set to 1000 in the second simulation.

    >>> model = Model(...)
    >>>
    >>> # Number of time-steps
    >>> steps = 1000
    >>>
    >>> # Boundary condition magnitude throughout the simulation
    >>> displacement_bc_array = np.linspace(2.5e-6, 2.5e-3, steps)
    >>>
    >>>  (u,
    >>>  ud,
    >>>  udd,
    >>>  force,
    >>>  body_force,
    >>>  damage,
    >>>  nlist,
    >>>  n_neigh) = model.simulate(
    >>>      ...displacement_bc_magnitudes=displacement_bc_array,
    >>>      ...)
    >>>
    >>> # Boundary condition magnitude throughout the simulation
    >>> displacement_bc_array = np.linspace(2.5025e-3, 5.0e-3, steps)
    >>>
    >>> u, *_ = model.simulate(
    >>>     u=u,
    >>>     ud=ud,
    >>>     connectivity=(nlist, n_neigh),
    >>>     steps=steps,
    >>>     first_step=1000,
    >>>     displacement_bc_magnitudes=displacement_bc_array,
    >>>     write=100
    >>>     )
