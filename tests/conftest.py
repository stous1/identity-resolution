"""Fixtures compartidas por las pruebas."""

import pandas as pd
import pytest


@pytest.fixture
def registros_pequenos() -> pd.DataFrame:
    """Seis registros de tres personas, con el formato de fake_1000."""
    return pd.DataFrame(
        {
            "unique_id": [0, 1, 2, 3, 4, 5],
            "first_name": ["Robert", "Rob", "Grace", "Grace", "Oliver", None],
            "surname": ["Allen", "Allen", "Kelly", "Kely", "Davies", "Davies"],
            "dob": [
                "1971-06-24",
                "1971-06-24",
                "1997-04-26",
                "1997-04-26",
                "2010-11-12",
                "2010-11-12",
            ],
            "city": ["London", "London", "Hull", None, "Leeds", "Leeds"],
            "email": [
                "robert@smith.net",
                None,
                "grace@jones.com",
                "grace@jones.com",
                None,
                "oliver@davies.org",
            ],
            "cluster": [0, 0, 1, 1, 2, 2],
        }
    )
