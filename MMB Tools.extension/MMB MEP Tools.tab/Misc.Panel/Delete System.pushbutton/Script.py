# -*- coding: utf-8 -*-
from pyrevit import revit
from Autodesk.Revit.DB import Transaction
from Autodesk.Revit.UI import Selection

doc = revit.doc
uidoc = revit.uidoc

def get_system_from_connectors(elem):
    """Return the first MEPSystem found via connectors."""
    cm = None
    try:
        cm = elem.ConnectorManager
    except:
        try:
            cm = elem.MEPModel.ConnectorManager
        except:
            pass
    if cm:
        for c in cm.Connectors:
            if c.MEPSystem:
                return c.MEPSystem
    return None

# --------------------------------------------------
# PICK ELEMENT
# --------------------------------------------------
try:
    ref = uidoc.Selection.PickObject(
        Selection.ObjectType.Element,
        "Select duct/pipe/fitting to delete its system"
    )
except:
    # user cancelled
    import sys
    sys.exit()

elem = doc.GetElement(ref.ElementId)

# --------------------------------------------------
# GET SYSTEM AND DELETE
# --------------------------------------------------
system = get_system_from_connectors(elem)

if system:
    t = Transaction(doc, "Delete MEP System")
    t.Start()
    doc.Delete(system.Id)
    t.Commit()
