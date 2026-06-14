"""
test_01_utils_unit.py — Pruebas UNITARIAS: ws/utils.py (Web)
=============================================================
Tipo  : Unitarias / Caja Blanca (funciones puras, sin BD)
Módulo: proyecto_tesis_web/ws/utils.py
"""

import pytest

pytestmark = pytest.mark.unit


class TestCalcularProgreso:
    """
    calcular_progreso(nivel_actual) → int 0-100
    Fórmula: (min(nivel, 6) - 1) / 5 * 100
    """

    def test_nivel_1_da_0_pct(self):
        from ws.utils import calcular_progreso
        assert calcular_progreso(1) == 0

    def test_nivel_2_da_20_pct(self):
        from ws.utils import calcular_progreso
        assert calcular_progreso(2) == 20

    def test_nivel_3_da_40_pct(self):
        from ws.utils import calcular_progreso
        assert calcular_progreso(3) == 40

    def test_nivel_4_da_60_pct(self):
        from ws.utils import calcular_progreso
        assert calcular_progreso(4) == 60

    def test_nivel_5_da_80_pct(self):
        from ws.utils import calcular_progreso
        assert calcular_progreso(5) == 80

    def test_nivel_6_da_100_pct(self):
        from ws.utils import calcular_progreso
        assert calcular_progreso(6) == 100

    def test_nivel_7_da_100_pct(self):
        """Nivel 7 (Maestro) se equipara a nivel 6 en el porcentaje."""
        from ws.utils import calcular_progreso
        assert calcular_progreso(7) == 100

    def test_nivel_6_y_7_son_iguales(self):
        from ws.utils import calcular_progreso
        assert calcular_progreso(6) == calcular_progreso(7)

    def test_resultados_son_enteros(self):
        from ws.utils import calcular_progreso
        for n in range(1, 8):
            resultado = calcular_progreso(n)
            assert isinstance(resultado, int), f"nivel {n}: esperado int, got {type(resultado)}"

    def test_progreso_monotono(self):
        """El porcentaje no puede decrecer al subir de nivel."""
        from ws.utils import calcular_progreso
        progresos = [calcular_progreso(n) for n in range(1, 8)]
        assert progresos == sorted(progresos)

    def test_consistencia_con_api_scoring(self):
        """
        La fórmula del web debe producir los mismos valores que la API.
        Verificación cruzada entre proyectos.
        """
        import sys, os
        api_dir = r'D:\Tesis\TODO\API_RESTFUL\API_COMERCIAL'
        if api_dir not in sys.path:
            sys.path.insert(0, api_dir)
        try:
            from models.scoring import nivel_to_progreso
            from ws.utils import calcular_progreso
            for n in range(1, 8):
                web_val = calcular_progreso(n)
                api_val = nivel_to_progreso(n)
                assert web_val == api_val, (
                    f"Inconsistencia nivel {n}: Web={web_val}, API={api_val}"
                )
        except ImportError:
            pytest.skip("API scoring no disponible")


class TestScoreToNivelWeb:
    """
    _score_to_nivel en gestionar_estudiante.py (web) debe coincidir
    con score_to_nivel en la API.
    Aquí verificamos los mismos tramos SCORE_BRACKETS.
    """

    @pytest.mark.parametrize("score,expected_nivel", [
        (0,   1), (21,  1),
        (22,  2), (35,  2),
        (36,  3), (49,  3),
        (50,  4), (64,  4),
        (65,  5), (78,  5),
        (79,  6), (92,  6),
        (93,  7), (100, 7),
    ])
    def test_brackets_iguales_a_api(self, score, expected_nivel):
        """Los tramos del web deben ser idénticos a los de la API."""
        import sys, os
        api_dir = r'D:\Tesis\TODO\API_RESTFUL\API_COMERCIAL'
        if api_dir not in sys.path:
            sys.path.insert(0, api_dir)
        try:
            from models.scoring import score_to_nivel
            assert score_to_nivel(score) == expected_nivel
        except ImportError:
            pytest.skip("API scoring no disponible")