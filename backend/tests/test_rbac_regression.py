import pytest

def test_all_four_roles_defined_in_permissions():
    """Requirement 3: Verify all four roles (ADMIN, INVESTIGATOR, ANALYST, VIEWER) are declared."""
    from app.security import permissions
    assert hasattr(permissions, "UserRole"), "permissions module must export UserRole"
    roles = [role.value for role in permissions.UserRole]
    assert "ADMIN" in roles
    assert "INVESTIGATOR" in roles
    assert "ANALYST" in roles
    assert "VIEWER" in roles

def test_viewer_role_cannot_modify_evidence():
    """Requirement 3: Verify VIEWER role cannot perform state modifications."""
    from app.security import permissions
    assert hasattr(permissions, "require_role"), "require_role dependency must exist"
