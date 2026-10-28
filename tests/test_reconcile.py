"""Unit tests for plate-reconciliation helpers (Phase 2).

Candidate mappings between the two inspections' plate numberings are
generated from the 8 dihedral symmetries of the tank layout: for each
transform, plate p maps to the plate whose center lands nearest to the
transformed center of p.
"""
import pytest

from tankfloor.normalize.reconcile import symmetry_mappings

# A tiny synthetic layout: 4 plates in a 2x2 grid around the center (0, 0)
# in tank inches. Centers: 1=(-50,50) 2=(50,50) 3=(-50,-50) 4=(50,-50).
CENTERS = {1: (-50.0, 50.0), 2: (50.0, 50.0), 3: (-50.0, -50.0), 4: (50.0, -50.0)}


class TestSymmetryMappings:
    def test_identity_present_and_correct(self):
        maps = symmetry_mappings(CENTERS)
        assert maps["identity"] == {1: 1, 2: 2, 3: 3, 4: 4}

    def test_mirror_east_west(self):
        maps = symmetry_mappings(CENTERS)
        assert maps["mirror_x"] == {1: 2, 2: 1, 3: 4, 4: 3}

    def test_rotate_180(self):
        maps = symmetry_mappings(CENTERS)
        assert maps["rot180"] == {1: 4, 2: 3, 3: 2, 4: 1}

    def test_eight_transforms(self):
        maps = symmetry_mappings(CENTERS)
        assert len(maps) == 8
        # every mapping is a permutation of the plates
        for name, m in maps.items():
            assert sorted(m) == [1, 2, 3, 4], name
            assert sorted(m.values()) == [1, 2, 3, 4], name
