import knime_extension as knext
import ifcopenshell
import ifcopenshell.util.unit
import ifcopenshell.geom
import pandas as pd
import numpy as np
import os
from .categories import category

from OCC.Core.BRepClass3d import BRepClass3d_SolidClassifier
from OCC.Core.TopAbs import TopAbs_IN
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.gp import gp_Pnt
from OCC.Core.BRepBndLib import brepbndlib


@knext.node(
    name="IFC Room Points",
    node_type=knext.NodeType.MANIPULATOR,
    icon_path="icons/ifc.png",
    category=category,
    after="",
)
@knext.input_table(name="Rooms IFC File", description="Table containing paths to the IFC file with rooms")
@knext.output_table(name="Room Points Table", description="Points inside room volumes with metadata")
class ExtractRoomVolumePoints:
    """
    Extracts interior points within each IfcSpace volume using OpenCascade geometry.
    Coordinates are always output in millimeters regardless of IFC model units.

    The buffer zone (minimum offset from room surfaces) is enforced geometrically
    via the OCC solid classifier tolerance, not via bounding-box shrinkage, so it
    works correctly for rotated or non-rectangular rooms.
    """

    path_column = knext.ColumnParameter(
        "IFC Path Column",
        "Column containing the path to the IFC file",
        port_index=0,
    )

    spacing = knext.DoubleParameter(
        "Grid Spacing [mm]",
        "Spacing between grid points along each axis",
        default_value=300,
    )

    min_offset_mm = knext.IntParameter(
        "Minimum Offset from Boundary [mm]",
        "Points closer than this distance to any room surface are discarded. "
        "Enforced via OCC classifier tolerance — geometrically correct for any room shape.",
        default_value=100,
    )

    def _get_storey(self, space):
        """
        Returns (storey_name, elevation_raw_model_units, storey_global_id).
        Checks Decomposes (IFC4 pattern) then ContainedInStructure (IFC2x3 pattern).
        """
        for rel in getattr(space, "Decomposes", []):
            s = rel.RelatingObject
            if s.is_a("IfcBuildingStorey"):
                elev = getattr(s, "Elevation", None)
                return getattr(s, "Name", None), (float(elev) if elev is not None else None), s.GlobalId
        for rel in getattr(space, "ContainedInStructure", []):
            s = rel.RelatingStructure
            if s.is_a("IfcBuildingStorey"):
                elev = getattr(s, "Elevation", None)
                return getattr(s, "Name", None), (float(elev) if elev is not None else None), s.GlobalId
        return None, None, None

    def _get_interior_points(self, space, spacing_mm, min_offset_mm, scale_to_mm):
        """
        Generates a 3D grid inside the space BRep and returns points that are
        at least min_offset_mm from any room surface.

        All internal geometry is in model units; output coordinates are in mm.
        The buffer is enforced by the OCC classifier tolerance, not by AABB shrinkage,
        so it is correct for rotated and non-rectangular rooms.
        """
        settings = ifcopenshell.geom.settings()
        settings.set("USE_WORLD_COORDS", True)
        settings.set("USE_PYTHON_OPENCASCADE", True)

        # Convert mm parameters to model units
        spacing_model = spacing_mm / scale_to_mm
        min_offset_model = min_offset_mm / scale_to_mm

        try:
            shape = ifcopenshell.geom.create_shape(settings, space)
            brep_shape = shape.geometry

            bbox = Bnd_Box()
            brepbndlib.Add(brep_shape, bbox)
            xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()

            classifier = BRepClass3d_SolidClassifier(brep_shape)

            x_coords = np.arange(xmin, xmax, spacing_model)
            y_coords = np.arange(ymin, ymax, spacing_model)
            z_coords = np.arange(zmin + spacing_model, zmax, spacing_model)

            # Small z offset for the XY pre-check — well inside the room, near the floor
            floor_z = zmin + spacing_model * 0.1

            points = []
            for x in x_coords:
                for y in y_coords:
                    # Pre-check: skip XY columns outside the room footprint (fast path)
                    classifier.Perform(gp_Pnt(x, y, floor_z), 1e-9)
                    if classifier.State() != TopAbs_IN:
                        continue
                    for z in z_coords:
                        # Geometric buffer enforced via classifier tolerance:
                        # TopAbs_IN only if point is > min_offset_model from any surface
                        classifier.Perform(gp_Pnt(x, y, z), min_offset_model)
                        if classifier.State() == TopAbs_IN:
                            points.append((x * scale_to_mm, y * scale_to_mm, z * scale_to_mm))

            return points

        except Exception as e:
            print(f"[WARN] Could not process space {getattr(space, 'GlobalId', '?')}: {e}")
            return []

    def configure(self, configure_context, input_schema_1):
        return None

    def execute(self, exec_context, input_1):
        df = input_1.to_pandas()

        if df.empty:
            raise ValueError("The input table is empty.")

        ifc_path = df[self.path_column].iloc[0]

        if not os.path.exists(ifc_path):
            raise ValueError(f"File not found: {ifc_path}")

        ifc_file = ifcopenshell.open(ifc_path)

        scale_to_m = ifcopenshell.util.unit.calculate_unit_scale(ifc_file)
        scale_to_mm = scale_to_m * 1000.0
        print(f"[INFO] IFC unit scale -> mm: {scale_to_mm}")

        spaces = ifc_file.by_type("IfcSpace")
        print(f"[INFO] Spaces to process: {len(spaces)}")

        data = []

        for space in spaces:
            try:
                storey_name, storey_elev_raw, storey_gid = self._get_storey(space)
                storey_elev_mm = storey_elev_raw * scale_to_mm if storey_elev_raw is not None else None
                long_name = getattr(space, "LongName", None)

                points = self._get_interior_points(space, self.spacing, self.min_offset_mm, scale_to_mm)
                print(f"[INFO] Space {getattr(space, 'GlobalId', '?')} ({long_name}): {len(points)} points")

                for x_mm, y_mm, z_mm in points:
                    data.append([
                        x_mm, y_mm, z_mm,
                        space.GlobalId,
                        storey_name,
                        storey_elev_mm,
                        storey_gid,
                        long_name,
                    ])

            except Exception as e:
                print(f"[WARN] Error processing space {getattr(space, 'GlobalId', '?')}: {e}")
                continue

        result_df = pd.DataFrame(
            data,
            columns=["X", "Y", "Z", "GlobalID", "Level", "StoreyElevation", "StoreyGlobalId", "LongName"],
        )
        return knext.Table.from_pandas(result_df)
