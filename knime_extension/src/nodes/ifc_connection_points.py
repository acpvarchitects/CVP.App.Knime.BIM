import knime_extension as knext
import ifcopenshell
import ifcopenshell.util.placement
import ifcopenshell.util.unit
import pandas as pd
import numpy as np
from .categories import category


# ===========================================================================
# Module-level helpers (outside the class to avoid issues with @knext.node
# which replaces the class with a wrapped object at decoration time)
# ===========================================================================

def _get_mm_scale(model) -> float:
    """
    Returns the factor to convert model-unit coordinates to millimeters.
    Model in mm -> returns 1.0
    Model in m  -> returns 1000.0
    """
    scale_to_m = ifcopenshell.util.unit.calculate_unit_scale(model)
    return scale_to_m * 1000.0


def _get_storey(element):
    """
    Walks ContainedInStructure to find the IfcBuildingStorey for an element.
    Returns (name, elevation_raw, global_id) or (None, None, None).
    Elevation is in model units; the caller scales to mm.
    """
    rels = getattr(element, "ContainedInStructure", None)
    if not rels:
        return None, None, None
    for rel in rels:
        s = rel.RelatingStructure
        if s.is_a("IfcBuildingStorey"):
            name = getattr(s, "Name", None)
            elev = getattr(s, "Elevation", None)
            return name, (float(elev) if elev is not None else None), s.GlobalId
    return None, None, None


def _get_bbox_center_local(element):
    """
    Returns the BoundingBox center in local (element) coordinates (model units),
    or None if no BoundingBox representation is available.
    """
    if not element.Representation:
        return None
    for rep in element.Representation.Representations:
        if rep.RepresentationType == "BoundingBox":
            for item in rep.Items:
                if item.is_a("IfcBoundingBox"):
                    corner = np.array(item.Corner.Coordinates, dtype=float)
                    dims = np.array(
                        [float(item.XDim), float(item.YDim), float(item.ZDim)]
                    )
                    return corner + dims / 2.0
    return None


def _compute_offset_points(element, scale_to_mm, offset_mm):
    """
    Computes the two offset points (Offset_Pos, Offset_Neg) in world mm.

    Strategy:
    1. Get world placement matrix via get_local_placement (accumulates full chain).
    2. Use local Y axis (matrix[:3, 1]) as the wall-perpendicular direction.
    3. Compute BoundingBox center in world space; fall back to placement origin.
    4. Apply +/- offset along the Y axis.

    Returns (pos_mm, neg_mm) as np.ndarray, or None if geometry is degenerate.
    """
    if not element.ObjectPlacement:
        return None

    matrix = ifcopenshell.util.placement.get_local_placement(element.ObjectPlacement)

    # Wall-perpendicular direction = local Y axis
    y_axis = matrix[:3, 1].copy()
    norm = np.linalg.norm(y_axis)
    if norm < 1e-9:
        return None
    y_axis /= norm  # unit vector, dimensionless

    # Center point in world coordinates (mm)
    center_local = _get_bbox_center_local(element)
    if center_local is not None:
        # Transform local bbox center to world (model units) then convert to mm
        center_world_mm = (matrix[:3, :3] @ center_local + matrix[:3, 3]) * scale_to_mm
    else:
        # Fallback: use the placement origin
        center_world_mm = matrix[:3, 3] * scale_to_mm

    pos = center_world_mm + y_axis * offset_mm
    neg = center_world_mm - y_axis * offset_mm
    return pos, neg


def _get_wall_host(element):
    """
    Traverses FillsVoids -> VoidsElements to find the host wall of a door or window.
    Returns the host IfcWall/IfcWallStandardCase, or None if not wall-hosted
    (e.g. skylights in roofs, trapdoors in slabs).
    """
    fills_voids = getattr(element, "FillsVoids", None)
    if not fills_voids:
        return None
    host_opening = fills_voids[0].RelatingOpeningElement
    rel_voids = getattr(host_opening, "VoidsElements", None)
    if not rel_voids:
        return None
    host = rel_voids[0].RelatingBuildingElement
    if host.is_a("IfcWall") or host.is_a("IfcWallStandardCase"):
        return host
    return None


def _collect_elements(model, include_doors, include_windows, include_openings, include_curtain_walls):
    """
    Returns a list of (element, element_type_label, storey_tuple).
    storey_tuple = (name, elevation_raw_model_units, global_id)

    Only horizontal connections through vertical wall elements are collected:
    - IfcDoor / IfcWindow: must be hosted by IfcWall/IfcWallStandardCase
      (excludes skylights in roofs and trapdoors in slabs)
    - IfcOpeningElement: must void an IfcWall/IfcWallStandardCase
    - IfcCurtainWall: treated as a single monolithic connection element

    Note: model.by_type() includes subtypes by default, so IfcDoor already
    covers IfcDoorStandardCase (IFC4) without a separate query.
    """
    collected = []

    if include_doors:
        try:
            for e in model.by_type("IfcDoor"):
                if _get_wall_host(e) is None:
                    continue
                collected.append((e, "IfcDoor", _get_storey(e)))
        except Exception as ex:
            print(f"[WARN] Could not query IfcDoor: {ex}")

    if include_windows:
        try:
            for e in model.by_type("IfcWindow"):
                if _get_wall_host(e) is None:
                    continue
                collected.append((e, "IfcWindow", _get_storey(e)))
        except Exception as ex:
            print(f"[WARN] Could not query IfcWindow: {ex}")

    if include_openings:
        try:
            for opening in model.by_type("IfcOpeningElement"):
                # Skip openings filled by a door or window (IfcBuildingElementProxy
                # from Revit Generic Models with voids must NOT be skipped)
                fillings = getattr(opening, "HasFillings", None)
                if fillings and any(
                    f.RelatedBuildingElement.is_a("IfcDoor")
                    or f.RelatedBuildingElement.is_a("IfcWindow")
                    for f in fillings
                ):
                    continue
                # Only consider openings that void a wall
                rel_voids = getattr(opening, "VoidsElements", None)
                if not rel_voids:
                    continue
                wall = rel_voids[0].RelatingBuildingElement
                if not (wall.is_a("IfcWall") or wall.is_a("IfcWallStandardCase")):
                    continue
                collected.append((opening, "IfcOpeningElement", _get_storey(wall)))
        except Exception as ex:
            print(f"[WARN] Could not query IfcOpeningElement: {ex}")

    if include_curtain_walls:
        try:
            for e in model.by_type("IfcCurtainWall"):
                collected.append((e, "IfcCurtainWall", _get_storey(e)))
        except Exception as ex:
            print(f"[WARN] Could not query IfcCurtainWall: {ex}")

    return collected


# ===========================================================================
# KNIME node
# ===========================================================================

_OUTPUT_COLUMNS = [
    "X", "Y", "Z",
    "GlobalID",
    "ElementType",
    "PointType",
    "Level",
    "StoreyElevation",
    "StoreyGlobalId",
]

_OUTPUT_DTYPES = {
    "X": "float64",
    "Y": "float64",
    "Z": "float64",
    "GlobalID": "object",
    "ElementType": "object",
    "PointType": "object",
    "Level": "object",
    "StoreyElevation": "float64",
    "StoreyGlobalId": "object",
}


@knext.node(
    name="IFC Connection Points XYZ",
    node_type=knext.NodeType.MANIPULATOR,
    icon_path="icons/ifc.png",
    category=category,
    after="",
)
@knext.input_table(name="IFC Path Table", description="Table containing IFC model paths")
@knext.output_table(
    name="Connection Points",
    description="Offset points for IFC connection elements (Doors, Windows, Openings). "
                "Coordinates are always in millimeters regardless of IFC model units.",
)
class IFCConnectionPointsExtractor:
    """
    Extracts pairs of offset points (positive and negative) for elements that
    represent connections between rooms: IfcDoor, IfcWindow, and unfilled
    IfcOpeningElement (openings in walls not filled by any door or window).

    The offset direction is the local Y axis of each element, which is always
    perpendicular to the host wall face in IFC.

    Output coordinates are always in millimeters. The node auto-detects whether
    the IFC model is authored in meters or millimeters and converts accordingly.
    """

    path_column = knext.ColumnParameter(
        "IFC Path Column",
        "Column containing the path to the IFC file",
        port_index=0,
    )

    offset_distance_mm = knext.DoubleParameter(
        "Offset Distance [mm]",
        "Distance from the element center to each offset point, along the wall-perpendicular axis",
        default_value=800.0,
    )

    include_doors = knext.BoolParameter(
        "Include IfcDoor",
        "Process IfcDoor elements (includes IfcDoorStandardCase subtypes automatically)",
        default_value=True,
    )

    include_windows = knext.BoolParameter(
        "Include IfcWindow",
        "Process IfcWindow elements (includes IfcWindowStandardCase subtypes automatically)",
        default_value=False,
    )

    include_openings = knext.BoolParameter(
        "Include IfcOpeningElement (unfilled only)",
        "Process IfcOpeningElement in walls that are NOT filled by any door or window",
        default_value=True,
    )

    include_curtain_walls = knext.BoolParameter(
        "Include IfcCurtainWall",
        "Process each IfcCurtainWall as a single monolithic connection element",
        default_value=True,
    )

    def configure(self, configure_context, input_schema):
        return None

    def execute(self, exec_context, input_table):
        df = input_table.to_pandas()

        if df.empty:
            raise ValueError("The input table is empty.")
        if self.path_column not in df.columns:
            raise ValueError(
                f"Column '{self.path_column}' not found in the input table."
            )

        ifc_path = df[self.path_column].iloc[0]
        model = ifcopenshell.open(ifc_path)

        scale_to_mm = _get_mm_scale(model)
        offset_mm = self.offset_distance_mm

        print(f"[INFO] IFC unit scale -> mm: {scale_to_mm}")
        print(f"[INFO] Offset distance: {offset_mm} mm")

        elements = _collect_elements(
            model,
            self.include_doors,
            self.include_windows,
            self.include_openings,
            self.include_curtain_walls,
        )
        print(f"[INFO] Elements to process: {len(elements)}")

        data = []

        for element, elem_type, (storey_name, storey_elev_raw, storey_gid) in elements:
            try:
                result = _compute_offset_points(element, scale_to_mm, offset_mm)
                if result is None:
                    print(
                        f"[WARN] Degenerate geometry, skipped: "
                        f"{elem_type} {getattr(element, 'GlobalId', '?')}"
                    )
                    continue

                pos, neg = result
                storey_elev_mm = (
                    storey_elev_raw * scale_to_mm
                    if storey_elev_raw is not None
                    else None
                )

                for pt, label in [(pos, "Offset_Pos"), (neg, "Offset_Neg")]:
                    data.append([
                        float(pt[0]),
                        float(pt[1]),
                        float(pt[2]),
                        element.GlobalId,
                        elem_type,
                        label,
                        storey_name,
                        storey_elev_mm,
                        storey_gid,
                    ])

            except Exception as e:
                print(
                    f"[WARN] Error processing {elem_type} "
                    f"{getattr(element, 'GlobalId', '?')}: {e}"
                )
                continue

        print(f"[INFO] Output rows: {len(data)}")

        result_df = pd.DataFrame(data, columns=_OUTPUT_COLUMNS)

        # Enforce explicit dtypes so an empty result stays compatible
        # with downstream nodes (e.g. K Nearest Neighbor expects float64 for X/Y/Z)
        for col, dtype in _OUTPUT_DTYPES.items():
            result_df[col] = result_df[col].astype(dtype)

        return knext.Table.from_pandas(result_df)
