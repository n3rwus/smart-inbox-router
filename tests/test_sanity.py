def test_workspace_packages_are_importable() -> None:
    import common
    import notifier
    import router

    assert all(m.__name__ for m in (common, notifier, router))
