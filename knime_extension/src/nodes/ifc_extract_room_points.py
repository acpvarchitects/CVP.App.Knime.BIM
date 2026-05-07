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
    Output coordinates are always in millimeters.

    UNIT CONVENTION (important):
    ifcopenshell.geom.create_shape with USE_PYTHON_OPENCASCADE=True always returns
    OCC geometry in SI meters, regardless of the IFC project unit (mm, m, etc.).
    All OCC operations (bbox, classifier, grid) are therefore done in meters.
    The local placement matrix from get_local_placement is in IFC project units and
    must be scaled to meters before being used with OCC coordinates.

    The grid and buffer are generated in the room's LOCAL coordinate system
    (via the element placement matrix) so that the buffer is aligned with room
    walls and is correct even for rotated rooms.
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
        "Points closer than this distance to any room wall (in local room coordinates) are discarded.",
        default_value=100,
    )

    def _get_storey(self, space):
        """Returns (storey_name, elevation_raw_model_units, storey_global_id)."""
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

    def _get_interior_points(self, space, spacing_mm, min_offset_mm):
        """
        Returns a list of (x_mm, y_mm, z_mm) interior points for the given IfcSpace.

        Works entirely in OCC world coordinates. Emits diagnostic lines for the first
        space to help verify OCC unit scale and classifier behaviour.
        """
        settings = ifcopenshell.geom.settings()
        settings.set("USE_WORLD_COORDS", True)
        settings.set("USE_PYTHON_OPENCASCADE", True)

        # OCC geometry is in SI meters; convert user parameters accordingly.
        spacing_m  = spacing_mm  / 1000.0
        min_offset_m = min_offset_mm / 1000.0

        gid = getattr(space, "GlobalId", "?")

        try:
            shape     = ifcopenshell.geom.create_shape(settings, space)
            brep      = shape.geometry

            bbox = Bnd_Box()
            brepbndlib.Add(brep, bbox)
            x0, y0, z0, x1, y1, z1 = bbox.Get()

            dx, dy, dz = x1 - x0, y1 - y0, z1 - z0

            # Diagnostic: printed only for the very first space per execute() call.
            # Tells us OCC scale (expect metres → dx ~3-30 for typical rooms) and
            # whether the classifier sees the bbox centre as inside the solid.
            if getattr(self, "_diag_done", False) is False:
                self._diag_done = True
                cx, cy, cz = (x0+x1)/2, (y0+y1)/2, (z0+z1)/2
                _cls = BRepClass3d_SolidClassifier(brep)
                _cls.Perform(gp_Pnt(cx, cy, cz), 1e-6)
                from OCC.Core.TopAbs import TopAbs_IN as _IN, TopAbs_OUT as _OUT, TopAbs_ON as _ON
                state_name = {_IN: "IN", _OUT: "OUT", _ON: "ON"}.get(_cls.State(), str(_cls.State()))
                print(f"[DIAG] First space {gid}: bbox dx={dx:.4f} dy={dy:.4f} dz={dz:.4f} "
                      f"(expected ~metres for typical rooms)")
                print(f"[DIAG] Classifier at bbox centre ({cx:.3f},{cy:.3f},{cz:.3f}): {state_name}")

            # Check room fits the requested buffer
            if dx < 2*min_offset_m or dy < 2*min_offset_m or dz < 2*min_offset_m:
                print(f"[WARN] Room too small for buffer {min_offset_mm}mm "
                      f"(bbox {dx*1000:.0f}x{dy*1000:.0f}x{dz*1000:.0f}mm): {gid}")
                return []

            # Grid in world coordinates with buffer applied to AABB
            xs = np.arange(x0 + min_offset_m, x1 - min_offset_m, spacing_m)
            ys = np.arange(y0 + min_offset_m, y1 - min_offset_m, spacing_m)
            zs = np.arange(z0 + min_offset_m, z1 - min_offset_m, spacing_m)

            if len(xs) == 0 or len(ys) == 0 or len(zs) == 0:
                return []

            # Floor pre-check z: just above the OCC bbox floor
            z_floor = z0 + spacing_m * 0.1

            classifier = BRepClass3d_SolidClassifier(brep)

            points = []
            for x in xs:
                for y in ys:
                    classifier.Perform(gp_Pnt(x, y, z_floor), 1e-6)
                    if classifier.State() != TopAbs_IN:
                        continue
                    for z in zs:
                        classifier.Perform(gp_Pnt(x, y, z), 1e-6)
                        if classifier.State() == TopAbs_IN:
                            # OCC coords are in metres → output in mm
                            points.append((x * 1000.0, y * 1000.0, z * 1000.0))

            return points

        except Exception as e:
            print(f"[WARN] Could not process space {gid}: {e}")
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

        scale_to_mm = ifcopenshell.util.unit.calculate_unit_scale(ifc_file) * 1000.0
        print(f"[INFO] IFC unit scale -> mm: {scale_to_mm}")

        spaces = ifc_file.by_type("IfcSpace")
        print(f"[INFO] Spaces to process: {len(spaces)}")

        data = []

        for space in spaces:
            try:
                storey_name, storey_elev_raw, storey_gid = self._get_storey(space)
                storey_elev_mm = (
                    storey_elev_raw * scale_to_mm if storey_elev_raw is not None else None
                )
                long_name = getattr(space, "LongName", None)

                points = self._get_interior_points(
                    space, self.spacing, self.min_offset_mm
                )
                print(
                    f"[INFO] Space {getattr(space, 'GlobalId', '?')} ({long_name}): "
                    f"{len(points)} points"
                )

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
