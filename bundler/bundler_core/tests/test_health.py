def test_health_sync() -> None:
    # Arrange
    from bundler_core import health

    # Act
    result = health()

    # Assert
    assert result == {"status": "ok"}

    # Cleanup
    # No cleanup needed; this test is read-only.

