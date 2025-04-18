import numpy as np
import pytest
from openff.toolkit import ForceField, Molecule, Topology, unit
from openff.utilities import has_package, skip_if_missing

from openff.interchange import Interchange
from openff.interchange._tests import (
    HAS_GROMACS,
    HAS_LAMMPS,
    MoleculeWithConformer,
    get_test_file_path,
    needs_gmx,
    needs_lmp,
)
from openff.interchange.constants import kj_mol
from openff.interchange.drivers import get_openmm_energies
from openff.interchange.foyer._guard import has_foyer

if has_package("openmm"):
    import openmm
    import openmm.app
    import openmm.unit

if HAS_GROMACS:
    from openff.interchange.drivers.gromacs import (
        _get_mdp_file,
        _process,
        _run_gmx_energy,
        get_gromacs_energies,
    )
if HAS_LAMMPS:
    from openff.interchange.drivers.lammps import get_lammps_energies


@pytest.mark.skipif(not has_foyer, reason="Foyer is not installed")
class TestEnergies:
    @pytest.fixture(scope="session")
    def oplsaa(self):
        import foyer

        return foyer.forcefields.load_OPLSAA()

    @skip_if_missing("mbuild")
    @needs_gmx
    @needs_lmp
    @pytest.mark.xfail
    @pytest.mark.parametrize("constrained", [True, False])
    @pytest.mark.parametrize("mol_smi", ["C"])  # ["C", "CC"]
    def test_energies_single_mol(self, constrained, sage, sage_unconstrained, mol_smi):
        import mbuild as mb

        molecule = MoleculeWithConformer.from_smiles(mol_smi, name="FOO")

        force_field = sage if constrained else sage_unconstrained

        interchange = Interchange.from_smirnoff(force_field, [molecule])

        interchange.collections["Electrostatics"].periodic_potential = "cutoff"

        molecule.to_file("out.xyz", file_format="xyz")
        compound = mb.load("out.xyz")
        packed_box = mb.fill_box(
            compound=compound,
            n_compounds=1,
            box=mb.Box(lengths=[10, 10, 10]),
        )

        positions = packed_box.xyz * unit.nanometer
        interchange.positions = positions

        omm_energies = get_openmm_energies(interchange, round_positions=8)

        mdp = "cutoff_hbonds" if constrained else "auto"
        # Compare GROMACS writer and OpenMM export
        gmx_energies = get_gromacs_energies(interchange, mdp=mdp)

        tolerances = {
            "Electrostatics": 2 * openmm.unit.kilojoule_per_mole,
            "vdW": 2 * openmm.unit.kilojoule_per_mole,
            "Nonbonded": 2 * openmm.unit.kilojoule_per_mole,
        }

        gmx_energies.compare(
            omm_energies,
            tolerances,
        )

        if not constrained:
            other_energies = get_openmm_energies(
                interchange,
                round_positions=8,
                hard_cutoff=True,
                electrostatics=True,
            )
            lmp_energies = get_lammps_energies(interchange)
            tolerances = {
                "vdW": 5.0 * openmm.unit.kilojoule_per_mole,
                "Electrostatics": 5.0 * openmm.unit.kilojoule_per_mole,
            }
            lmp_energies.compare(other_energies, tolerances)

    @needs_gmx
    @pytest.mark.skipif(not has_foyer, reason="Foyer is not installed")
    @skip_if_missing("mbuild")
    def test_process_rb_torsions(self, oplsaa):
        """Test that the GROMACS driver reports Ryckaert-Bellemans torsions"""
        from mbuild import Box

        from openff.interchange.components.mbuild import offmol_to_compound

        ethanol = MoleculeWithConformer.from_smiles("CCO")
        ethanol.generate_unique_atom_names()

        my_compound = offmol_to_compound(ethanol)
        my_compound.box = Box(lengths=[4, 4, 4])

        struct = oplsaa.apply(my_compound)

        struct.save("eth.top", overwrite=True)
        struct.save("eth.gro", overwrite=True)

        # Get single-point energies using GROMACS
        oplsaa_energies = _process(
            _run_gmx_energy(
                top_file="eth.top",
                gro_file="eth.gro",
                mdp_file=_get_mdp_file("default"),
            ),
        )

        assert oplsaa_energies.energies["RBTorsion"].m != 0.0

    @needs_gmx
    def test_gmx_14_energies_exist(self, sage):
        # TODO: Make sure 1-4 energies are accurate, not just existent

        # Use a molecule with only one 1-4 interaction, and
        # make it between heavy atoms because H-H 1-4 are weak
        mol = MoleculeWithConformer.from_smiles("ClC#CCl", name="HPER")

        out = Interchange.from_smirnoff(sage, [mol])
        out.positions = mol.conformers[0]
        out.box = 3 * [10]

        # Put this molecule in a large box with cut-off electrostatics
        # to prevent it from interacting with images of itself
        out["Electrostatics"].periodic_potential = "cutoff"

        gmx_energies = get_gromacs_energies(out)

        # The only possible non-bonded interactions should be from 1-4 intramolecular interactions
        assert gmx_energies.energies["vdW"].m != 0.0
        assert gmx_energies.energies["Electrostatics"].m != 0.0

        # TODO: It would be best to save the 1-4 interactions, split off into vdW and Electrostatics
        # in the energies. This might be tricky/intractable to do for engines that are not GROMACS

    @needs_gmx
    @needs_lmp
    def test_cutoff_electrostatics(self):
        ion_ff = ForceField(get_test_file_path("ions.offxml"))
        ions = Topology.from_molecules(
            [
                Molecule.from_smiles("[#3+]"),
                Molecule.from_smiles("[#17-]"),
            ],
        )
        out = Interchange.from_smirnoff(ion_ff, ions)
        out.box = [4, 4, 4] * unit.nanometer

        gmx = []
        lmp = []

        for d in np.linspace(0.75, 0.95, 5):
            positions = np.zeros((2, 3)) * unit.nanometer
            positions[1, 0] = d * unit.nanometer
            out.positions = positions

            out["Electrostatics"].periodic_potential = "cutoff"
            gmx.append(
                get_gromacs_energies(out, mdp="auto").energies["Electrostatics"].m,
            )
            lmp.append(
                get_lammps_energies(out).energies["Electrostatics"].m_as(unit.kilojoule / unit.mol),
            )

        assert np.sum(np.sqrt(np.square(np.asarray(lmp) - np.asarray(gmx)))) < 1e-3

    @pytest.mark.parametrize(
        "smi",
        [
            "c1cc(ccc1c2ccncc2)O",
            "c1cc(ccc1c2ccncc2)[O-]",
            "c1cc(c(cc1O)Cl)c2cc[nH+]cc2",
        ],
    )
    @needs_gmx
    @pytest.mark.slow
    def test_interpolated_parameters(self, smi):
        xml_ff_bo_all_heavy_bonds = """<?xml version='1.0' encoding='ASCII'?>
        <SMIRNOFF version="0.3" aromaticity_model="OEAroModel_MDL">
          <Bonds version="0.3" fractional_bondorder_method="AM1-Wiberg" fractional_bondorder_interpolation="linear">
            <Bond smirks="[!#1:1]~[!#1:2]" id="bbo1"
                k_bondorder1="100.0 * kilocalories_per_mole/angstrom**2"
                k_bondorder2="1000.0 * kilocalories_per_mole/angstrom**2"
                length_bondorder1="1.5 * angstrom"
                length_bondorder2="1.0 * angstrom"/>
          </Bonds>
        </SMIRNOFF>
        """

        molecule = MoleculeWithConformer.from_smiles(smi)

        forcefield = ForceField(
            "openff-2.0.0.offxml",
            xml_ff_bo_all_heavy_bonds,
        )

        out = Interchange.from_smirnoff(forcefield, [molecule])
        out.box = [4, 4, 4] * unit.nanometer
        out.positions = molecule.conformers[0]

        for key in ["Bond", "Torsion"]:
            interchange_energy = get_openmm_energies(
                out,
                combine_nonbonded_forces=True,
            ).energies[key]

            gromacs_energy = get_gromacs_energies(out).energies[key]
            energy_diff = abs(interchange_energy - gromacs_energy).m_as(kj_mol)

            if energy_diff < 1e-6:
                pass
            elif energy_diff < 1e-2:
                pytest.xfail(
                    f"Found {key} energy difference of {energy_diff} kJ/mol between GROMACS and OpenMM exports",
                )
            else:
                pytest.fail(
                    f"Found {key} energy difference of {energy_diff} kJ/mol between GROMACS and OpenMM exports",
                )

    @needs_gmx
    def test_rb_torsion_energies(self, monkeypatch):
        monkeypatch.setenv("INTERCHANGE_EXPERIMENTAL", "1")

        interchange = Interchange.from_gromacs(
            get_test_file_path("gromacs/rb_torsions.top"),
            get_test_file_path("gromacs/rb_torsions.gro"),
        )

        openmm_energy = get_openmm_energies(interchange)["RBTorsion"]
        gromacs_energy = get_gromacs_energies(interchange)["RBTorsion"]

        assert abs(openmm_energy - gromacs_energy).m_as(unit.kilojoule_per_mole) < 1e-4
