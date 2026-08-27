from core.workforce_scope import canonical_client_name, canonical_position_name


def test_known_customer_typos_map_to_canonical_names():
    assert canonical_client_name('ommia fankfurt') == 'OMMIA Frankfurt'
    assert canonical_client_name('stadhaust am markt') == 'Stadthaus am Markt'
    assert canonical_client_name('Hoefel Catering Aschaffenburg') == 'Höfel Catering – Aschaffenburg'


def test_known_position_typos_map_to_canonical_names():
    assert canonical_position_name('Servicekrat') == 'Servicekraft'
    assert canonical_position_name('Houskeeping') == 'Housekeeping'
    assert canonical_position_name('Front-Office') == 'Front Office'
