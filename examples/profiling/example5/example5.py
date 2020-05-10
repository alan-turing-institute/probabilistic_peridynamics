"""
Created on Sun Nov 10 16:25:58 2019

@author: Ben Boys
"""
import argparse
import cProfile
from io import StringIO
import numpy as np
import pathlib
from peridynamics import OpenCL
from peridynamics.model import initial_crack_helper
from peridynamics.integrators import EulerCromer
from peridynamics.integrators import EulerCromerOptimised
from peridynamics.integrators import EulerCromerOptimisedLumped
from peridynamics.integrators import EulerCromerOptimisedLumped2
from pstats import SortKey, Stats
import time
import shutil
import os

os.environ['PYOPENCL_COMPILER_OUTPUT'] = '1'
os.environ['COMPUTE_PROFILE'] = '1'
# =============================================================================
# Choose platform:
# [0] <pyopencl.Platform 'Intel(R) OpenCL' at 0x1fc79552690>
# Choice [0]:0
# Choose device(s):
# [0] <pyopencl.Device 'Intel(R) UHD Graphics 620' on 'Intel(R) OpenCL' at 0x1fc793c5350>
# [1] <pyopencl.Device 'Intel(R) Core(TM) i7-8550U CPU @ 1.80GHz' on 'Intel(R) OpenCL' at 0x1fc79479ac0>
# Choice, comma-separated [0]:0
# Set the environment variable PYOPENCL_CTX='0:0' to avoid being asked again.
# =============================================================================
os.environ['PYOPENCL_CTX'] = '0:1'

@initial_crack_helper
def is_crack(x, y):
    output = 0
    return output

def is_tip(horizon, x):
    output = 0
    if x[0] > 1.650 - 0.2 * horizon:
        output = 1
    return output

def is_rebar(p):
    """ Function to determine whether the node coordinate is rebar
    """
    p = p[1:] # y and z coordinates for this node
    bar_centers = [
        # Compressive bars 25mm of cover
        np.array((0.031, 0.031)),
        np.array((0.219, 0.031)),

        # Tensile bars 25mm of cover
        np.array((0.03825, 0.569)),
        np.array((0.21175, 0.569))]

    rad_c = 0.006
    rad_t = 0.01325

    radii = [
        rad_c,
        rad_c,
        rad_t,
        rad_t]

    costs = [ np.sum(np.square(cent - p) - (np.square(rad))) for cent, rad in zip(bar_centers, radii) ]
    if any( c <= 0 for c in costs ):
        return True
    else:
        return False

def bond_type(x, y):
    """ 
    Determines bond type given pair of node coordinates.
    Usage:
        'plain = 1' will return a plain concrete bond for all bonds, an so a
    plain concrete beam.
        'plain = 0' will return a concrete beam with some rebar as specified
        in "is_rebar()"
    """
    plain = 0
    output = 0 # default to concrete
    bool1 = is_rebar(x)
    bool2 = is_rebar(y)
    if plain == 1:
        output = 'concrete'
    elif bool1 and bool2:
        output = 'steel'
    elif bool1 != bool2:
        output = 'interface'
    else:
        output = 'concrete'
    return output


def is_boundary(horizon, x):
    """
    Function which marks displacement boundary constrained particles
    2 is no boundary condition (the number here is an arbitrary choice)
    -1 is displacement loaded IN -ve direction
    1 is displacement loaded IN +ve direction
    0 is clamped boundary
    """
    bnd = [2, 2, 2]
    if x[0] < 0.2 * horizon:
        bnd[0] = 0
        bnd[1] = 0
        bnd[2] = 0
    return bnd

def is_forces_boundary(horizon, x):
    """
    Marks types of body force on the particles
    2 is no boundary condition (the number here is an arbitrary choice)
    -1 is force loaded IN -ve direction
    1 is force loaded IN +ve direction
    """
    bnd = [2, 2, 2]
    if x[0] > 1.65 - 0.2 * horizon:
        bnd[2] = -1
    return bnd

def boundary_function(model):
    """ 
    Initiates displacement boundary conditions,
    also define the 'tip' (for plotting displacements)
    """
    load_rate = 0
    # initiate
    model.bc_types = np.zeros((model.nnodes, model.degrees_freedom), dtype=np.intc)
    model.bc_values = np.zeros((model.nnodes, model.degrees_freedom), dtype=np.float64)
    model.tip_types = np.zeros(model.nnodes, dtype=np.intc)

    # Find the boundary nodes and apply the displacement values
    for i in range(0, model.nnodes):
        # Define boundary types and values
        bnd = is_boundary(model.horizon, model.coords[i][:])
        model.bc_types[i, 0] = np.intc(bnd[0])
        model.bc_types[i, 1] = np.intc(bnd[1])
        model.bc_types[i, 2] = np.intc((bnd[2]))
        model.bc_values[i, 0] = np.float64(bnd[0] * 0.5 * load_rate)
        model.bc_values[i, 1] = np.float64(bnd[1] * 0.5 * load_rate)
        model.bc_values[i, 2] = np.float64(bnd[2] * 0.5 * load_rate)
        # Define tip here
        tip = is_tip(model.horizon, model.coords[i][:])
        model.tip_types[i] = np.intc(tip)

def boundary_forces_function(model):
    """ 
    Initiates boundary forces. The units are force per unit volume.
    """
    model.force_bc_types = np.zeros((model.nnodes, model.degrees_freedom), dtype=np.intc)
    model.force_bc_values = np.zeros((model.nnodes, model.degrees_freedom), dtype=np.float64)

    # Find the force boundary nodes and find amount of boundary nodes
    num_force_bc_nodes = 0
    for i in range(0, model.nnodes):
        bnd = is_forces_boundary(model.horizon, model.coords[i][:])
        if -1 in bnd:
            num_force_bc_nodes += 1
        elif 1 in bnd:
            num_force_bc_nodes += 1
        model.force_bc_types[i, 0] = np.intc((bnd[0]))
        model.force_bc_types[i, 1] = np.intc((bnd[1]))
        model.force_bc_types[i, 2] = np.intc((bnd[2]))
    #print('number of force loaded nodes is ', num_force_bc_nodes)
    model.num_force_bc_nodes = num_force_bc_nodes
    for i in range(0, model.nnodes):
        for j in range(model.dimensions):
            bnd = model.force_bc_types[i,j]
            if bnd != 2:
                # apply the force bc value, which is total reaction force / (num loaded nodes * node volume)
                # units are force per unit volume
                model.force_bc_values[i, j] = np.float64(bnd * model.max_reaction / (model.num_force_bc_nodes * model.V[i]))

def main():
    """
    3D canteliver beam peridynamics simulation
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh_file_name", help="run example on a given mesh file name")
    parser.add_argument('--optimised', action='store_const', const=True)
    parser.add_argument('--profile', action='store_const', const=True)
    parser.add_argument('--lumped', action='store_const', const=True)
    parser.add_argument('--lumped2', action='store_const', const=True)
    args = parser.parse_args()

    if args.profile:
        profile = cProfile.Profile()
        profile.enable()

    beams = [
        '1650beam792.msh',
        '1650beam2652.msh',
        '1650beam3570.msh',
        '1650beam4095.msh',
        '1650beam6256.msh',
        '1650beam15840.msh',
        '1650beam32370.msh',
        '1650beam74800.msh',
        '1650beam144900.msh',
        '1650beam247500.msh',
        '1650beam792t.msh',
        '1650beam2652t.msh',
        '1650beam3570t.msh',
        '1650beam4095t.msh',
        '1650beam6256t.msh',
        '1650beam15840t.msh',
        '1650beam32370t.msh',
        '1650beam74800t.msh',
        '1650beam144900t.msh',
        '1650beam247500t.msh',
        '3300beam952.msh',
        '3300beam2970.msh',
        '3300beam4392.msh',
        '3300beam6048.msh',
        '3300beam11836.msh',
        '3300beam17600.msh',
        '3300beam31680.msh',
        '3300beam64350.msh',
        '3300beam149600.msh',
        '3300beam495000.msh',
        '3300beam952t.msh',
        '3300beam2970t.msh',
        '3300beam4392t.msh',
        '3300beam6048t.msh',
        '3300beam11836t.msh',
        '3300beam17600t.msh',
        '3300beam31680t.msh',
        '3300beam64350t.msh',
        '3300beam149600t.msh',
        '3300beam495000t.msh']
    assert args.mesh_file_name in beams, 'mesh_file_name = {} was not recognised, please check the mesh file is in the directory'.format(args.mesh_file_name)

    mesh_file = pathlib.Path(__file__).parent.absolute() / args.mesh_file_name
    st = time.time()

    # Set simulation parameters
    volume_total = 1.65 * 0.6 * 0.25
    density_concrete = 2400
    youngs_modulus_concrete = 1.*22e9
    youngs_modulus_steel = 1.*210e9
    poisson_ratio = 0.25
    strain_energy_release_rate_concrete = 100
    strain_energy_release_rate_steel = 13000
    networks = {'1650beam792.msh': 'Network1650beam792.vtk',
                '1650beam2652.msh': 'Network1650beam2652.vtk',
                '1650beam3570.msh': 'Network1650beam3570.vtk',
                '1650beam4095.msh': 'Network1650beam4095.vtk',
                '1650beam6256.msh': 'Network1650beam6256.vtk',
                '1650beam15840.msh': 'Network1650beam15840.vtk',
                '1650beam32370.msh': 'Network1650beam32370.vtk',
                '1650beam74800.msh': 'Network1650beam74800.vtk',
                '1650beam144900.msh': 'Network1650beam144900.vtk',
                '1650beam247500.msh': 'Network1650beam247500.vtk',
                '1650beam792t.msh': 'Network1650beam792t.vtk',
                '1650beam2652t.msh': 'Network1650beam2652t.vtk',
                '1650beam3570t.msh': 'Network1650beam3570t.vtk',
                '1650beam4095t.msh': 'Network1650beam4095t.vtk',
                '1650beam6256t.msh': 'Network1650beam6256t.vtk',
                '1650beam15840t.msh': 'Network1650beam15840t.vtk',
                '1650beam32370t.msh': 'Network1650beam32370t.vtk',
                '1650beam74800t.msh': 'Network1650beam74800t.vtk',
                '1650beam144900t.msh': 'Network1650beam144900t.vtk',
                '1650beam247500t.msh': 'Network1650beam247500t.vtk',
                '3300beam952.msh': 'Network3300beam952.vtk',
                '3300beam2970.msh': 'Network3300beam2970.vtk',
                '3300beam4392.msh': 'Network3300beam4392.vtk',
                '3300beam6048.msh': 'Network3300beam6048.vtk',
                '3300beam11836.msh': 'Network3300beam11836.vtk',
                '3300beam17600.msh': 'Network3300beam17600.vtk',
                '3300beam31680.msh': 'Network3300beam31680.vtk',
                '3300beam64350.msh': 'Network3300beam64350.vtk',
                '3300beam149600.msh': 'Network3300beam149600.vtk',
                '3300beam495000.msh': 'Network3300beam495000.vtk',
                '3300beam952t.msh': 'Network3300beam952t.vtk',
                '3300beam2970t.msh': 'Network3300beam2970t.vtk',
                '3300beam4392t.msh': 'Network3300beam4392t.vtk',
                '3300beam6048t.msh': 'Network3300beam6048t.vtk',
                '3300beam11836t.msh': 'Network3300beam11836t.vtk',
                '3300beam17600t.msh': 'Network3300beam17600t.vtk',
                '3300beam31680t.msh': 'Network3300beam31680t.vtk',
                '3300beam64350t.msh': 'Network3300beam64350t.vtk',
                '3300beam149600t.msh': 'Network3300beam149600t.vtk',
                '3300beam495000t.msh': 'Network3300beam495000t.vtk'}
    network_file_name = networks[args.mesh_file_name]
    dxs = {'1650beam792.msh': 0.075,
           '1650beam2652.msh': 0.0485,
           '1650beam3570.msh': 0.0485,
           '1650beam4095.msh': 0.0423,
           '1650beam6256.msh': 0.0359,
           '1650beam15840.msh': 0.025,
           '1650beam32370.msh': 0.020,
           '1650beam74800.msh': 0.015,
           '1650beam144900.msh': 0.012,
           '1650beam247500.msh': 0.010,
           '1650beam792t.msh': 0.075,
           '1650beam2652t.msh': 0.0485,
           '1650beam3570t.msh': 0.0485,
           '1650beam4095t.msh': 0.0423,
           '1650beam6256t.msh': 0.0359,
           '1650beam15840t.msh': 0.025,
           '1650beam32370t.msh': 0.020,
           '1650beam74800t.msh': 0.015,
           '1650beam144900t.msh': 0.012,
           '1650beam247500t.msh': 0.010,
           '3300beam952.msh': 0.0971,
           '3300beam2970.msh': 0.0611,
           '3300beam4392.msh': 0.0541,
           '3300beam6048.msh': 0.0458,
           '3300beam11836.msh': 0.0357,
           '3300beam17600.msh': 0.0313,
           '3300beam31680.msh': 0.0250,
           '3300beam64350.msh': 0.0200,
           '3300beam149600.msh': 0.0150,
           '3300beam495000.msh': 0.0100,
           '3300beam952t.msh': 0.0971,
           '3300beam2970t.msh': 0.0611,
           '3300beam4392t.msh': 0.0541,
           '3300beam6048t.msh': 0.0458,
           '3300beam11836t.msh': 0.0357,
           '3300beam17600t.msh': 0.0313,
           '3300beam31680t.msh': 0.0250,
           '3300beam64350t.msh': 0.0200,
           '3300beam149600t.msh': 0.0150,
           '3300beam495000t.msh': 0.0100}
    dx = dxs[args.mesh_file_name]
    horizon = dx * np.pi 
    # Two materials in this example, that is 'concrete' and 'steel'
    # Critical strain, s0
    critical_strain_concrete = np.double(np.power(
            np.divide(5*strain_energy_release_rate_concrete, 6*youngs_modulus_steel*horizon),
            (1./2)
            ))
    critical_strain_steel = np.double(np.power(
    np.divide(5*strain_energy_release_rate_steel, 6*youngs_modulus_steel*horizon),
    (1./2)
    ))
    damping = 2.0e6 # damping term
    # Peridynamic bond stiffness, c
    bulk_modulus_concrete = youngs_modulus_concrete/ (3* (1 - 2*poisson_ratio))
    bulk_modulus_steel = youngs_modulus_steel / (3* (1- 2*poisson_ratio))
    bond_stiffness_concrete = (
    np.double((18.00 * bulk_modulus_concrete) /
    (np.pi * np.power(horizon, 4)))
    )
    bond_stiffness_steel = (
    np.double((18.00 * bulk_modulus_steel) /
    (np.pi * np.power(horizon, 4)))
    )
    crack_length = np.double(0.0)
    model = OpenCL(mesh_file_name = args.mesh_file_name, 
                   density = density_concrete, 
                   horizon = horizon,
                   damping = damping,
                   bond_stiffness_concrete = bond_stiffness_concrete,
                   bond_stiffness_steel = bond_stiffness_steel, 
                   critical_strain_concrete = critical_strain_concrete,
                   critical_strain_steel = critical_strain_steel,
                   crack_length = crack_length,
                   volume_total=volume_total,
                   bond_type=bond_type,
                   network_file_name = network_file_name,
                   initial_crack=[],
                   dimensions=3,
                   transfinite=1,
                   precise_stiffness_correction=0)
    saf_fac = 0.5 # Typical values 0.70 to 0.95 (Sandia PeridynamicSoftwareRoadmap) 0.5
    model.dt = (
     0.8 * np.power( 2.0 * density_concrete * dx / 
     (np.pi * np.power(model.horizon, 2.0) * dx * model.bond_stiffness_concrete), 0.5)
     * saf_fac
     )
    model.max_reaction = 500000 # in newtons, about 85 times self weight
    model.load_scale_rate = 1/500000

    # Set force and displacement boundary conditions
    boundary_function(model)
    boundary_forces_function(model)
    
    if args.optimised:
        if args.lumped:
            integrator = EulerCromerOptimisedLumped(model)
            method = 'EulerCromerOptimisedLumped'
        elif args.lumped2:
            integrator = EulerCromerOptimisedLumped2(model)
            method = 'EulerCromerOptimisedLumped2'
        else:
            integrator = EulerCromerOptimised(model)
            method = 'EulerCromerOptimised'
    else:
        integrator = EulerCromer(model)
        method = 'EulerCromer'

    # delete output directory contents, this is probably unsafe?
    shutil.rmtree('./output', ignore_errors=False)
    os.mkdir('./output')

    damage_sum_data, tip_displacement_data, tip_shear_force_data = model.simulate(model, sample=1, steps=1000, integrator=integrator, write=1000, toolbar=0)
    print(args.mesh_file_name, method)
    print('damage_sum_data', damage_sum_data)
    print('tip_displacement_data', tip_displacement_data)
    print('tip_shear_force_data', tip_shear_force_data)
    print('TOTAL TIME REQUIRED {}'.format(time.time() - st))
    if args.profile:
        profile.disable()
        s = StringIO()
        stats = Stats(profile, stream=s).sort_stats(SortKey.CUMULATIVE)
        stats.print_stats()
        print(s.getvalue())
    print('\n')

if __name__ == "__main__":
    main()