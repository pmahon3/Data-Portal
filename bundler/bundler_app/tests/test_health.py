def test_health_sync() -> None:
    # Arrange
    from app.api import health

    # Act
    result = health()

    # Assert
    assert result == {"status": "ok"}

    # Cleanup
    # No cleanup needed; this test is read-only.

