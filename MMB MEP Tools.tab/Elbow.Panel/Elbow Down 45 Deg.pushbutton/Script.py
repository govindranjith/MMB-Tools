# -*- coding: utf-8 -*-
from pyrevit import revit, script
from Autodesk.Revit.DB import (
    XYZ, Transaction, BuiltInParameter,
    UnitUtils, UnitTypeId, MEPCurve, LocationCurve
)
from Autodesk.Revit.DB.Mechanical import Duct
from Autodesk.Revit.DB.Plumbing import Pipe
from Autodesk.Revit.DB.Electrical import Conduit
from Autodesk.Revit.UI import Selection

doc = revit.doc
uidoc = revit.uidoc
logger = script.get_logger()

# ------------------------------------------------------------------------------
# Pick element + click point
# ------------------------------------------------------------------------------
try:
    ref = uidoc.Selection.PickObject(Selection.ObjectType.Element, "Select a duct, pipe or conduit")
    click_pt = ref.GlobalPoint
except:
    script.exit()

elem = doc.GetElement(ref.ElementId)
if not isinstance(elem, MEPCurve):
    script.exit()

mep_curve = elem

# ------------------------------------------------------------------------------
# Find nearest open connector to click
# ------------------------------------------------------------------------------
connectors = mep_curve.ConnectorManager.Connectors
closest_conn = None
min_dist = float("inf")
for conn in connectors:
    if conn.IsConnected: continue
    d = conn.Origin.DistanceTo(click_pt)
    if d < min_dist:
        min_dist = d
        closest_conn = conn
if not closest_conn:
    script.exit()

# ------------------------------------------------------------------------------
# Stub length rules
# ------------------------------------------------------------------------------
def compute_stub_length(elem):
    if isinstance(elem, Conduit):
        return UnitUtils.ConvertToInternalUnits(1.0, UnitTypeId.Meters)

    size_mm = 0.0
    if isinstance(elem, Duct):
        dia = elem.get_Parameter(BuiltInParameter.RBS_CURVE_DIAMETER_PARAM)
        width = elem.get_Parameter(BuiltInParameter.RBS_CURVE_WIDTH_PARAM)
        if dia and dia.HasValue:
            size_mm = UnitUtils.ConvertFromInternalUnits(dia.AsDouble(), UnitTypeId.Millimeters)
        elif width and width.HasValue:
            size_mm = UnitUtils.ConvertFromInternalUnits(width.AsDouble(), UnitTypeId.Millimeters)
    elif isinstance(elem, Pipe):
        dia = elem.get_Parameter(BuiltInParameter.RBS_PIPE_DIAMETER_PARAM)
        if dia and dia.HasValue:
            size_mm = UnitUtils.ConvertFromInternalUnits(dia.AsDouble(), UnitTypeId.Millimeters)

    if size_mm <= 500: meters = 2.0
    elif size_mm <= 1000: meters = 4.0
    elif size_mm <= 1500: meters = 6.0
    elif size_mm <= 2000: meters = 8.0
    elif size_mm <= 2500: meters = 10.0
    elif size_mm <= 3000: meters = 12.0
    elif size_mm <= 3500: meters = 14.0
    elif size_mm <= 4000: meters = 16.0
    elif size_mm <= 4500: meters = 18.0
    elif size_mm <= 5000: meters = 20.0
    else: meters = 25.0

    return UnitUtils.ConvertToInternalUnits(meters, UnitTypeId.Meters)

segment_length = compute_stub_length(mep_curve)

# ------------------------------------------------------------------------------
# 45° down vector: always downward relative to connector
# ------------------------------------------------------------------------------
cs = closest_conn.CoordinateSystem

# Take connector's facing axis in XY as horizontal
hvec = XYZ(cs.BasisZ.X, cs.BasisZ.Y, 0)   # BasisZ is the connector's forward
if hvec.IsZeroLength():
    hvec = XYZ.BasisX
hvec = hvec.Normalize()

# Combine with global -Z to force downward tilt
down_45 = (hvec + XYZ(0, 0, -1)).Normalize()

start_pt = closest_conn.Origin
end_pt = start_pt + down_45.Multiply(segment_length)
level = doc.GetElement(mep_curve.ReferenceLevel.Id)

# ------------------------------------------------------------------------------
# Helper: nearest connector pair
# ------------------------------------------------------------------------------
def get_nearest_connectors(set1, set2):
    min_d = float("inf")
    pair = (None, None)
    for c1 in set1:
        if c1.IsConnected: continue
        for c2 in set2:
            if c2.IsConnected: continue
            d = c1.Origin.DistanceTo(c2.Origin)
            if d < min_d:
                min_d = d
                pair = (c1, c2)
    return pair

# ------------------------------------------------------------------------------
# Transaction
# ------------------------------------------------------------------------------
t = Transaction(doc, "Elbow Down 45°")
t.Start()

try:
    if isinstance(mep_curve, Duct):
        new_curve = Duct.Create(
            doc,
            mep_curve.MEPSystem.GetTypeId(),
            mep_curve.DuctType.Id,
            level.Id,
            start_pt,
            end_pt
        )
        # Copy parent sizes directly
        for bip in [BuiltInParameter.RBS_CURVE_WIDTH_PARAM,
                    BuiltInParameter.RBS_CURVE_HEIGHT_PARAM,
                    BuiltInParameter.RBS_CURVE_DIAMETER_PARAM]:
            p = mep_curve.get_Parameter(bip)
            if p and p.HasValue:
                new_curve.get_Parameter(bip).Set(p.AsDouble())

    elif isinstance(mep_curve, Pipe):
        new_curve = Pipe.Create(
            doc,
            mep_curve.MEPSystem.GetTypeId(),
            mep_curve.PipeType.Id,
            level.Id,
            start_pt,
            end_pt
        )
        dia_param = mep_curve.get_Parameter(BuiltInParameter.RBS_PIPE_DIAMETER_PARAM)
        if dia_param and dia_param.HasValue:
            new_curve.get_Parameter(BuiltInParameter.RBS_PIPE_DIAMETER_PARAM).Set(dia_param.AsDouble())

    elif isinstance(mep_curve, Conduit):
        new_curve = Conduit.Create(
            doc,
            mep_curve.GetTypeId(),
            start_pt,
            end_pt,
            level.Id
        )
        dia_param = mep_curve.get_Parameter(BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM)
        if dia_param and dia_param.HasValue:
            new_curve.get_Parameter(BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM).Set(dia_param.AsDouble())

    # Connect with elbow
    c1, c2 = get_nearest_connectors(mep_curve.ConnectorManager.Connectors, new_curve.ConnectorManager.Connectors)
    if c1 and c2:
        doc.Create.NewElbowFitting(c1, c2)

    t.Commit()
    logger.info("✅ Elbow Down 45° created at connector nearest to mouse click, pointing downward.")

except Exception as ex:
    t.RollBack()
    logger.error("❌ Transaction failed: {}".format(ex))
    raise
