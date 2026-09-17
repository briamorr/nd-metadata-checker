from checker import diff_downloads

A = {"Name": "nd-metadata.tar.gz", "ReleaseDate": "2026-09-15", "Description": "a"}
B = {"Name": "ndi-metadata.ni", "ReleaseDate": "2026-09-15", "Description": "b"}


def test_first_run_is_a_change():
    diff = diff_downloads(None, [A])
    assert diff["first_run"] and diff["changed"]
    assert diff["current"] == [A]


def test_no_change():
    diff = diff_downloads([A, B], [A, B])
    assert not diff["changed"] and not diff["first_run"]


def test_added():
    diff = diff_downloads([A], [A, B])
    assert diff["changed"] and diff["added"] == [B]


def test_removed():
    diff = diff_downloads([A, B], [A])
    assert diff["changed"] and diff["removed"] == [B]


def test_release_date_bump():
    bumped = {**A, "ReleaseDate": "2026-10-01"}
    diff = diff_downloads([A], [bumped])
    assert diff["changed"]
    assert diff["updated"][0]["fields"] == ["ReleaseDate"]
    assert diff["updated"][0]["current"] == bumped
