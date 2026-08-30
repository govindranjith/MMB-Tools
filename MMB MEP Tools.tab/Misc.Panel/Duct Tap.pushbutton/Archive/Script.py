# -*- coding: utf-8 -*-
"""
Tap LT - pyRevit tool for Revit 2025

Workflow:
1. Select the main duct.
2. Select the branch duct.
3. The closest available branch connector is identified.
4. Revit creates a take-off fitting between the branch and main duct.

Compatible with:
- Revit 2025
- pyRevit CPython 3
- pyRevit IronPython 2.7
"""

from pyrevit import revit, DB, UI, forms, script

from Autodesk.Revit.DB import (
    BuiltInCategory,
    ConnectorType,
    Domain,
    LocationCurve,
    Transaction
)

from Autodesk.Revit.DB.Mechanical import Duct
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

import traceback


# ============================================================
# PYREVIT AND REVIT REFERENCES
# ============================================================

uidoc = revit.uidoc
doc = revit.doc
output = script.get_output()


# ============================================================
# SETTINGS
# ============================================================

# If True, only an open/unconnected branch connector is accepted.
# This is recommended to prevent modifying existing connections.
REQUIRE_OPEN_BRANCH_CONNECTOR = True

# Small tolerance in Revit internal units, feet.
TOLERANCE = 1.0e-6


# ============================================================
# SELECTION FILTER
# ============================================================

class DuctSelectionFilter(ISelectionFilter):
    """Allow selection of regular Revit duct elements only."""

    def AllowElement(self, element):
        try:
            if element is None:
                return False

            if not isinstance(element, Duct):
                return False

            if element.Category is None:
                return False

            return (
                element.Category.Id.IntegerValue ==
                int(BuiltInCategory.OST_DuctCurves)
            )

        except:
            return False

    def AllowReference(self, reference, point):
        return False


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_connector_manager(element):
    """Return the connector manager belonging to an MEP curve."""

    try:
        return element.ConnectorManager
    except:
        pass

    try:
        return element.MEPModel.ConnectorManager
    except:
        return None


def get_end_connectors(element):
    """
    Return physical HVAC end connectors belonging to the element.
    Logical connectors are ignored.
    """

    connector_manager = get_connector_manager(element)

    if connector_manager is None:
        return []

    connectors = []

    for connector in connector_manager.Connectors:
        try:
            if connector.ConnectorType != ConnectorType.End:
                continue

            if connector.Domain != Domain.DomainHvac:
                continue

            connectors.append(connector)

        except:
            continue

    return connectors


def get_unconnected_end_connectors(element):
    """Return end connectors that are currently not connected."""

    result = []

    for connector in get_end_connectors(element):
        try:
            if not connector.IsConnected:
                result.append(connector)
        except:
            continue

    return result


def get_main_curve(main_duct):
    """Return the centreline curve of the main duct."""

    location = main_duct.Location

    if not isinstance(location, LocationCurve):
        raise Exception(
            "The selected main duct does not have a valid centreline."
        )

    curve = location.Curve

    if curve is None:
        raise Exception(
            "The main duct centreline could not be retrieved."
        )

    return curve


def distance_from_point_to_curve(point, curve):
    """
    Return the shortest distance from a point to the bounded duct curve.

    Curve.Project normally returns the closest position on the curve.
    A fallback checks the curve endpoints if projection is unavailable.
    """

    try:
        projection = curve.Project(point)

        if projection is not None:
            return point.DistanceTo(projection.XYZPoint)
    except:
        pass

    start_point = curve.GetEndPoint(0)
    end_point = curve.GetEndPoint(1)

    return min(
        point.DistanceTo(start_point),
        point.DistanceTo(end_point)
    )


def get_closest_branch_connector(branch_duct, main_duct):
    """
    Find the branch end connector closest to the main duct centreline.

    Open connectors are prioritised. If the REQUIRE_OPEN_BRANCH_CONNECTOR
    setting is True, connected connectors will not be considered.
    """

    main_curve = get_main_curve(main_duct)

    open_connectors = get_unconnected_end_connectors(branch_duct)

    if open_connectors:
        candidate_connectors = open_connectors

    elif REQUIRE_OPEN_BRANCH_CONNECTOR:
        raise Exception(
            "The selected branch duct has no open end connector.\n\n"
            "Disconnect one end of the branch duct and run the command again."
        )

    else:
        candidate_connectors = get_end_connectors(branch_duct)

    if not candidate_connectors:
        raise Exception(
            "No valid HVAC end connector was found on the branch duct."
        )

    closest_connector = None
    closest_distance = float("inf")

    for connector in candidate_connectors:
        try:
            distance = distance_from_point_to_curve(
                connector.Origin,
                main_curve
            )

            if distance < closest_distance:
                closest_distance = distance
                closest_connector = connector

        except:
            continue

    if closest_connector is None:
        raise Exception(
            "A suitable branch connector could not be identified."
        )

    return closest_connector, closest_distance


def validate_ducts(main_duct, branch_duct):
    """Validate the two selected duct elements."""

    if main_duct is None or branch_duct is None:
        raise Exception("Both the main duct and branch duct are required.")

    if main_duct.Id == branch_duct.Id:
        raise Exception(
            "The main duct and branch duct cannot be the same element."
        )

    if not isinstance(main_duct, Duct):
        raise Exception(
            "The first selected element is not a regular duct."
        )

    if not isinstance(branch_duct, Duct):
        raise Exception(
            "The second selected element is not a regular duct."
        )

    main_connectors = get_end_connectors(main_duct)
    branch_connectors = get_end_connectors(branch_duct)

    if not main_connectors:
        raise Exception(
            "The selected main duct has no valid HVAC connectors."
        )

    if not branch_connectors:
        raise Exception(
            "The selected branch duct has no valid HVAC connectors."
        )


def create_takeoff(main_duct, branch_connector):
    """
    Create the native Revit take-off fitting.

    The connector belongs to the branch duct.
    The MEP curve passed as the second argument is the main duct.
    """

    return doc.Create.NewTakeoffFitting(
        branch_connector,
        main_duct
    )


# ============================================================
# MAIN COMMAND
# ============================================================

def main():

    duct_filter = DuctSelectionFilter()

    try:
        main_reference = uidoc.Selection.PickObject(
            ObjectType.Element,
            duct_filter,
            "Select the MAIN duct"
        )

        main_duct = doc.GetElement(main_reference.ElementId)

        branch_reference = uidoc.Selection.PickObject(
            ObjectType.Element,
            duct_filter,
            "Select the BRANCH duct"
        )

        branch_duct = doc.GetElement(branch_reference.ElementId)

    except OperationCanceledException:
        return

    except Exception as selection_error:
        forms.alert(
            "Selection failed.\n\n{0}".format(selection_error),
            title="Tap LT",
            warn_icon=True
        )
        return

    try:
        validate_ducts(main_duct, branch_duct)

        branch_connector, connector_distance = (
            get_closest_branch_connector(
                branch_duct,
                main_duct
            )
        )

        transaction = Transaction(
            doc,
            "Tap LT - Connect Branch to Main Duct"
        )

        transaction.Start()

        try:
            takeoff = create_takeoff(
                main_duct,
                branch_connector
            )

            if takeoff is None:
                raise Exception(
                    "Revit did not return a take-off fitting."
                )

            doc.Regenerate()

            transaction.Commit()

        except:
            if transaction.HasStarted():
                transaction.RollBack()
            raise

        # Select the newly created tap fitting.
        try:
            uidoc.Selection.SetElementIds(
                [takeoff.Id]
            )
        except:
            pass

        # Silent exit
        return

    except Exception as creation_error:

        error_message = str(creation_error)

        detailed_message = (
            "The tap could not be created.\n\n"
            "{0}\n\n"
            "Please check the following:\n"
            "• The branch has an open end connector.\n"
            "• Both elements are regular ducts, not fabrication parts.\n"
            "• The main duct type has a valid take-off/junction "
            "routing preference.\n"
            "• A compatible tap family is loaded in the project.\n"
            "• The branch connector is within a practical distance "
            "of the main duct.\n"
            "• The branch angle is supported by the selected tap family."
        ).format(error_message)

        forms.alert(
            detailed_message,
            title="Tap LT",
            warn_icon=True
        )

        output.print_md("## Tap LT Error")
        output.print_md("**Error:** `{0}`".format(error_message))
        output.print_md("```")
        output.print_md(traceback.format_exc())
        output.print_md("```")


# ============================================================
# RUN COMMAND
# ============================================================

if __name__ == "__main__":
    main()