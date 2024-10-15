# Sharp edges

## Quirks of charge assignment

### Charge assignment hierarchy

Interchange, following the [SMIRNOFF specification](https://openforcefield.github.io/standards/standards/smirnoff/#partial-charge-and-electrostatics-models), assigns charges to (heavy) atoms with the following priority:

1. **Preset charges**: Look for molecule matches in the `charge_from_molecules` argument
2. **Library charges**: Look for chemical environment matches in the `<LibraryCharges>` section of the force field
3. **Charge increment models**: Look for chemical environment matches in the `<ChargeIncrementModel>` section of the force field
4. **AM1-BCC**: Try to run some variant of AM1-BCC (presumably this is were graph charges go) as described by the `<ToolkitAM1BCC>` section of the force field

If charges are successfully assigned using a method, no lower-priority methods in this list are attempted. For example:

* A force field with library charge parameters for peptides (i.e. a biopolymer force field, covering all appropriate residues) will NOT try to call AM1-BCC on a biopolymers.
* If a ligand is successfully assigned preset charges, chemical environment matching of library charges and charge increments will be skipped, as will AM1-BCC.
* If a variant of AM1-BCC (i.e. using something other than AM1 and/or using custom BCCs) is encoded in a `<ChargeIncrementModel>` section, other AM1-BCC implementations will not be called.
* If preset charges are not provided, a force field like OpenFF's Parsley or Sage lines without (many) library charges or charge increments will attempt AM1-BCC on all molecules (except water and monoatomic ions).

After all of these steps are complete and all heavy atoms given partial charges, virtual sites are assigned charges using the values of `charge_increment`s in the virtual site parameters. Because virtual site charge are only described by the force field, using preset charges with virtual sites is discouraged.

### Preset charges

The following restrictions are in place when using preset charges:

* All molecules in the the `charge_from_molecules` list must be non-isomorphic with each other.
* All molecules in the the `charge_from_molecules` list must have partial charges.

Using preset charges with virtual sites is discouraged as it can provide surprising results.

## Quirks of `from_openmm`

### Modified masses are ignored

The OpenFF Toolkit does not support isotopes or atomic masses other than the values defined in the periodic table. In the `Topology` and `Molecule` classes, particles masses are defined only by their atomic number. When topologies are read from OpenMM, the particle mass is ignored and the atomic number of the element is read and used to define the atomic properties.

As a consequence, any hydrogen mass repartitioning (HMR) applied to a system is "un-done" upon import --- mass is shifted back from hydrogens to their heavy atoms. To re-apply HMR (shift masses back to hydrogens), use the appropriate API at export time, typically with an export method's `hydrogen_mass` argument.

For updates, [search "HMR" in the issue tracker](https://github.com/search?q=repo%3Aopenforcefield%2Fopenff-interchange+hmr&type=issues&s=updated&o=desc) or raise a [new issue](https://github.com/openforcefield/openff-interchange/issues/new/choose).

Keywords: OpenMM, HMR, hydrogen mass repartioning

### Force constants of constrained bonds may be lost in conversions

Commonly, OpenMM systems prepared by other tools constrain bonds (i.e. bonds between hydrogen and heavy atoms) and/or use rigid water models. These topological bonds lack force constants, which are required by some other engines even though they do not affect the behavior of the simulation.

For example, consider an OpenMM system prepared, from the OpenMM API, with `ForceField.createSystem(..., constraints=HBonds, rigidWaters=True)` and then imported with `Interchange.from_openmm`. The constrained bonds, including all bonds in waters, don't contain physics parameters (particularly the force constant `k`). These parameters are typically dropped from the corresponding `HarmonicBondForce` when running OpenMM simulations with these sorts of constraints. When exporting this system to GROMACS or another engine that needs these parameters, the export will either crash due to missing parameters or silently write a file with some missing or blank parameters.

For more, see [issue #1005](https://github.com/openforcefield/openff-interchange/issues/1005#issue-2405679510).

Keywords: OpenMM, GROMACS, constraints, bond constraints, rigid water

## Quirks with GROMACS

### Residue indices must begin at 1

Whether by informal convention or official standard, residue numbers in GROMACS files begin at 1. Other tools may start the residue numbers at 0. If a topology contains residue numbers below 1, exporting to GROMACS will trigger an error (though not necessarily while exporting to other formats). A workaround for 0-indexed residue numbers is to simply increment all residue numbers by 1.

For more, see [issue #1007](https://github.com/openforcefield/openff-interchange/issues/1007)

Keywords: GROMACS, residue number, resnum, residue index
