"""Setup script for peridynamics."""
from setuptools import setup, find_packages, Extension
from Cython.Build import cythonize
import pathlib

# The directory containing this file
HERE = pathlib.Path(__file__).parent

# The text of the README file
README = (HERE / "README.md").read_text()

extra_compile_args = ['-O3']
extra_link_args = []

ext_modules = [
    Extension(
        "peripy.create_crack",
        ["peripy/create_crack.pyx"],
        extra_compile_args=extra_compile_args,
        extra_link_args=extra_link_args
        ),
    Extension(
        "peripy.peridynamics",
        ["peripy/peridynamics.pyx"],
        extra_compile_args=extra_compile_args,
        extra_link_args=extra_link_args
        ),
    Extension(
        "peripy.spatial",
        ["peripy/spatial.pyx"],
        extra_compile_args=extra_compile_args,
        extra_link_args=extra_link_args
        ),
    Extension(
        "peripy.correction",
        ["peripy/correction.pyx"],
        extra_compile_args=extra_compile_args,
        extra_link_args=extra_link_args
        )
    ]


setup(
    name="peripy",
    version="1.0.0",
    description="A fast OpenCL Peridynamics package for python",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/alan-turing-institute/Probabilistic-Peridynamics",
    author="Jim Madge, Ben Boys, Tim Dodwell, Greg Mingas",
    license="MIT",
    packages=find_packages(exclude=['*.test']),
    include_package_data=True,
    entry_points={
        'console_scripts': ['peripy=peripy.cli:main']
        },
    ext_modules=cythonize(ext_modules),
    install_requires=[
        'meshio',
        'numpy',
        'pyopencl',
        'scipy',
        'tqdm',
        'h5py',
        'sklearn',
        'tqdm',
        'sphinx_rtd_theme'
        ]
    )
