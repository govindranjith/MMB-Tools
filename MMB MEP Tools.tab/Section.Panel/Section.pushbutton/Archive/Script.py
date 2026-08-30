# -*- coding: utf-8 -*-

from pyrevit import revit, DB
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

doc = revit.doc
uidoc = revit.uidoc

# --------------------------------------------------
# SETTINGS
# --------------------------------------------------

END_OFFSET_MM = 300
TOP_BOTTOM_OFFSET_MM = 300
DEPTH_MM = 600

MM_TO_FT = 1.0 / 304.8

END_OFFSET = END_OFFSET_MM * MM_TO_FT
TOP_BOTTOM_OFFSET = TOP_BOTTOM_OFFSET_MM * MM_TO_FT
DEPTH = DEPTH_MM * MM_TO_FT

# --------------------------------------------------
# FILTER
# --------------------------------------------------

class MEPFilter(ISelectionFilter):

    def AllowElement(self, e):

        if not e.Category:
            return False

        catid = e.Category.Id.IntegerValue

        allowed = [
            int(DB.BuiltInCategory.OST_DuctCurves),
            int(DB.BuiltInCategory.OST_PipeCurves),
            int(DB.BuiltInCategory.OST_Conduit),
            int(DB.BuiltInCategory.OST_CableTray)
        ]

        return catid in allowed

    def AllowReference(self, ref, point):
        return False


# --------------------------------------------------
# SECTION TYPE
# --------------------------------------------------

def get_section_type():

    types = DB.FilteredElementCollector(doc)\
        .OfClass(DB.ViewFamilyType)

    for t in types:
        if t.ViewFamily == DB.ViewFamily.Section:
            return t

    return None


# --------------------------------------------------
# MAIN
# --------------------------------------------------

try:

    picked = uidoc.Selection.PickObject(
        ObjectType.Element,
        MEPFilter(),
        "Select duct / pipe / conduit / cable tray"
    )

except OperationCanceledException:
    raise SystemExit

elem = doc.GetElement(picked.ElementId)

loc = elem.Location

if not isinstance(loc, DB.LocationCurve):
    raise SystemExit

line = loc.Curve

p0 = line.GetEndPoint(0)
p1 = line.GetEndPoint(1)

direction = (p1 - p0).Normalize()

up = DB.XYZ.BasisZ

viewdir = direction.CrossProduct(up)

if viewdir.GetLength() < 0.001:
    raise SystemExit

viewdir = viewdir.Normalize()

mid = (p0 + p1) * 0.5

# --------------------------------------------------
# GET SIZE
# --------------------------------------------------

bbox = elem.get_BoundingBox(None)

height = bbox.Max.Z - bbox.Min.Z

if height < (300 * MM_TO_FT):
    height = 300 * MM_TO_FT

length = line.Length

# --------------------------------------------------
# SECTION BOX
# --------------------------------------------------

transform = DB.Transform.Identity

transform.Origin = mid
transform.BasisX = direction
transform.BasisY = up
transform.BasisZ = viewdir

sectionBox = DB.BoundingBoxXYZ()

sectionBox.Transform = transform

sectionBox.Min = DB.XYZ(
    -(length / 2.0) - END_OFFSET,
    -(height / 2.0) - TOP_BOTTOM_OFFSET,
    -DEPTH / 2.0
)

sectionBox.Max = DB.XYZ(
    (length / 2.0) + END_OFFSET,
    (height / 2.0) + TOP_BOTTOM_OFFSET,
    DEPTH / 2.0
)

section_type = get_section_type()

if not section_type:
    raise SystemExit

# --------------------------------------------------
# CREATE SECTION
# --------------------------------------------------

t = DB.Transaction(doc, "Section LT")

t.Start()

section = DB.ViewSection.CreateSection(
    doc,
    section_type.Id,
    sectionBox
)

try:
    section.CropBoxVisible = True
except:
    pass

try:
    section.CropBoxActive = True
except:
    pass

t.Commit()