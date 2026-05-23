"""
seed_ejercicios.py
Reemplaza los ejercicios existentes por 20 ejercicios REALES del libro
"Fichas de Matematica 3 - Secundaria" del MINEDU (edicion 2019/2024).

Todos los ejercicios tienen respuesta correcta = A.
Cada comentario indica la ficha y pagina del libro para encontrar la imagen.

Uso:
    python seed_ejercicios.py
"""

import psycopg

DATABASE_URL = "postgresql://postgres:hola1@localhost:5432/bd_ejemplo"

# ---------------------------------------------------------------------------
# Formato: (descripcion, id_competencia, pista, nivel_logro,
#           opcion_A(correcta), opcion_B, opcion_C, opcion_D)
#
# FUENTE DE IMAGEN:
#   Competencia 1 -> Ficha 5 p.62  (EJ1, EJ2, EJ5, EJ7, EJ8)
#                    Ficha 1 p.20  (EJ6 - imagen del neumatico de tractor)
#   Competencia 2 -> Ficha 2 p.29-30 (EJ1, EJ3, EJ7)
#                    Ficha 6 p.70    (EJ1, EJ2 - imagen mochila y estribos)
#   Competencia 3 -> Ficha 3 p.38-40 (EJ1 espejo, EJ2 juego mecanico, EJ8)
#                    Ficha 7 p.82-83 (EJ1 puente, EJ3 palmeras)
#   Competencia 4 -> Ficha 4 p.50-51 (EJ3 grafico circular ojos)
#                    Ficha 8 p.94    (EJ1, EJ3, EJ6, EJ8)
# ---------------------------------------------------------------------------

EJERCICIOS = [

    # ── Competencia 1: Resuelve problemas de cantidad (id=1) ─────────────────
    # Ficha 5, p.62, EJ1 - texto puro, sin imagen
    (
        "Patricia recibio un bono por su buen desempenio durante el ultimo anio "
        "y ha decidido ahorrarlo. ¿En cuanto se convertira su capital de S/ 12 000 "
        "al 5 % anual si se mantiene en el banco durante 2 anios y medio?",
        1,
        "Calcula el interes con la formula I = C x r x t, luego suma al capital. "
        "Convierte 2 anios y medio a 2.5 anios.",
        2,
        "S/ 13 500",
        "S/ 1 500",
        "S/ 600",
        "S/ 13 200",
    ),
    # Ficha 5, p.62, EJ2 - texto puro, sin imagen
    (
        "Sebastian junto un capital de S/ 20 000 y ha decidido darlo en prestamo "
        "para que genere intereses. ¿Cual es el interes que produce en 7 anios su "
        "capital, si lo presta con una tasa del 9 % de interes simple?",
        1,
        "Usa I = C x r x t. Asegurate de que la tasa y el tiempo esten en las "
        "mismas unidades (ambos en anios).",
        3,
        "S/ 12 600",
        "S/ 1 800",
        "S/ 32 600",
        "S/ 1 260",
    ),
    # Ficha 1, p.20, EJ6 - IMAGEN: foto del neumatico de tractor con tabla de tolerancias
    (
        "Los estandares internacionales fijan los limites de tolerancia de los "
        "neumaticos (Ancho: -2% hasta +4%; Diametro: -1% hasta +1,5%). Calcula el "
        "intervalo de tolerancia del ancho y del diametro para un neumatico cuyas "
        "medidas de fabricacion son 443,00 mm de ancho y 1654,00 mm de diametro.",
        1,
        "Aplica los porcentajes al valor nominal: limite inferior = valor x (1 - % inferior), "
        "limite superior = valor x (1 + % superior).",
        4,
        "Ancho: [434,14; 460,72] mm y Diametro: [1637,46; 1678,81] mm",
        "Ancho: [442,98; 443,04] mm y Diametro: [1653,99; 1654,02] mm",
        "Ancho: [441,00; 447,00] mm y Diametro: [1653,99; 1654,02] mm",
        "Ancho: [438,57; 443,40] mm y Diametro: [1653,00; 1655,50] mm",
    ),
    # Ficha 5, p.62, EJ5 - texto puro, sin imagen
    (
        "Una inmobiliaria tiene como meta ganar un interes simple de S/ 580 000 "
        "en un periodo de 2 anios y medio. ¿Cual debe ser el capital inicial que "
        "debe depositar si se sabe que la tasa de interes es del 4 % trimestral?",
        1,
        "Convierte la tasa trimestral a anual (multiplica por 4). Luego despeja "
        "el capital de la formula I = C x r x t.",
        5,
        "S/ 1 450 000",
        "S/ 5 800 000",
        "S/ 232 000",
        "S/ 120 833,33",
    ),
    # Ficha 5, p.62, EJ8 - texto puro, sin imagen
    (
        "El papa de Rolando decide comprar una camara digital. El modelo que necesita "
        "es ofrecido a credito por dos tiendas a un precio de S/ 1999: la tienda A "
        "cobra 10 % de interes simple mensual en 7 meses, y la tienda B cobra 15 % "
        "mensual en 4 meses. ¿Cuanto pagara de interes el papa de Rolando si escoge "
        "la mejor propuesta?",
        1,
        "Calcula el interes de cada tienda con I = C x r x t. La mejor propuesta "
        "es la que genera menos interes.",
        6,
        "S/ 1 199,40",
        "S/ 1 399,30",
        "S/ 799,60",
        "S/ 2 398,80",
    ),

    # ── Competencia 2: Regularidad, equivalencia y cambio (id=2) ────────────
    # Ficha 2, p.29, EJ1 - IMAGEN: ilustracion de tablero de ajedrez / jugadora
    (
        "Maritza es una jugadora de ajedrez que participo en las olimpiadas de su "
        "distrito. Ella recibio 1 punto por vencer a su primer contrincante, 2 puntos "
        "por el segundo, 4 por el tercero, y asi sucesivamente. Si en el torneo "
        "vencio a 16 de sus contrincantes, ¿cuantos puntos acumulo?",
        2,
        "Es una P.G. con a1=1 y r=2. Usa la formula de suma: Sn = a1 * (r^n - 1) / (r - 1).",
        2,
        "65 535 puntos",
        "1 024 puntos",
        "256 puntos",
        "16 384 puntos",
    ),
    # Ficha 2, p.30, EJ7 - texto puro, sin imagen
    (
        "La poblacion de una colonia de bacterias ha aumentado en progresion "
        "geometrica, de 59 049 bacterias el primer dia a 236 196 el tercer dia. "
        "¿Cual es la razon de crecimiento de la colonia por dia?",
        2,
        "Usa an = a1 * r^(n-1). Con a1=59049 y a3=236196, calcula r^2 = 236196/59049 "
        "y luego halla r.",
        3,
        "2",
        "0,5",
        "0,2",
        "1,5",
    ),
    # Ficha 2, p.29, EJ3 - texto puro, sin imagen
    (
        "La profesora Marisol reta a sus estudiantes con la siguiente pregunta: "
        "si en una progresion geometrica el noveno termino es igual a 5 y la razon "
        "es -1/3, ¿cual es el sexto termino?",
        2,
        "Usa a9 = a6 * r^3. Entonces a6 = a9 / r^3 = 5 / (-1/3)^3. Calcula (-1/3)^3 = -1/27.",
        4,
        "-135",
        "-32 805",
        "135",
        "328",
    ),
    # Ficha 6, p.70, EJ1 - IMAGEN: ilustracion de mochila escolar y espalda
    (
        "Diana es una estudiante del tercer grado de secundaria. Segun la OMS, "
        "cada estudiante puede llevar en su mochila el 10 % de su masa corporal o, "
        "como maximo, el 15 %, a fin de no desarrollar afecciones en la columna. "
        "Si Diana pesa 48 kg, ¿cuales son las posibles masas de su mochila para "
        "no afectar su salud?",
        2,
        "Calcula el 10 % y el 15 % de 48 kg para obtener los extremos del intervalo.",
        5,
        "Desde 4,8 kg hasta 7,2 kg",
        "Desde 2,08 kg hasta 7,28 kg",
        "Desde 2,08 kg hasta 8,2 kg",
        "Desde 1,8 kg hasta 7,7 kg",
    ),
    # Ficha 6, p.70, EJ2 - IMAGEN: foto de estribos de construccion
    (
        "Para construir una casa, se requiere un determinado numero de columnas. "
        "A su vez, estas necesitan un numero adecuado de estribos. Se sabe que, "
        "para armar una columna simple, se emplean entre 28 y 32 estribos. "
        "¿Cual es el maximo numero de estribos que se podrian utilizar si se van "
        "a armar 18 columnas simples?",
        2,
        "El maximo se obtiene usando el numero maximo de estribos por columna. "
        "Multiplica el maximo por columna por la cantidad de columnas.",
        6,
        "576",
        "505",
        "504",
        "575",
    ),

    # ── Competencia 3: Forma, movimiento y localizacion (id=3) ──────────────
    # Ficha 3, p.38, EJ1 - IMAGEN: fotografia de persona frente a un espejo
    (
        "Cuando una persona esta frente a un espejo plano, ¿que transformacion "
        "geometrica se observa?",
        3,
        "En un espejo, cada punto de la imagen esta a la misma distancia del espejo "
        "que el punto original, pero al lado opuesto. ¿Que transformacion produce eso?",
        1,
        "Simetria axial",
        "Rotacion",
        "Traslacion",
        "Simetria central",
    ),
    # Ficha 3, p.38, EJ2 - IMAGEN: fotografia de un juego mecanico tipo rueda
    (
        "¿Que tipo de transformacion geometrica se visualiza en la imagen del "
        "juego mecanico (rueda giratoria de feria)?",
        3,
        "Observa como se mueve cada punto del juego: todos giran alrededor de un "
        "punto fijo central.",
        3,
        "Rotacion",
        "Traslacion",
        "Simetria axial",
        "Simetria central",
    ),
    # Ficha 3, p.40, EJ8 - texto puro, sin imagen necesaria
    (
        "Realizar una ampliacion del 80 % en una fotocopiadora es como aplicar "
        "una homotecia con centro en una de las esquinas de la hoja. ¿A cuanto "
        "equivale la razon de esa homotecia?",
        3,
        "La razon de homotecia k es el cociente entre el tamano final y el tamano "
        "original. Una ampliacion del 80 % significa que el resultado es el 80 % "
        "del original.",
        4,
        "4/5",
        "5/4",
        "9/5",
        "5/9",
    ),
    # Ficha 7, p.82, EJ1 - IMAGEN: figura geometrica del puente con triangulos semejantes
    (
        "El alcalde de una comunidad tiene como proyecto construir un puente sobre "
        "un rio. Segun los datos del grafico (dos triangulos semejantes formados por "
        "los lados del rio: catetos de 5 m y 12 m en el triangulo pequenio, y base "
        "de 48 m en el triangulo grande), ¿cual sera la longitud del puente?",
        3,
        "Usa la proporcionalidad de triangulos semejantes: el cociente de lados "
        "correspondientes es constante. Plantea 12/48 = 5/puente.",
        4,
        "20 m",
        "12,5 m",
        "1,25 m",
        "2 m",
    ),
    # Ficha 7, p.83, EJ3 - IMAGEN: figura de palmera con cuerda y estaca (triangulo rectangulo)
    (
        "Carlos cuida las palmeras del Plan Verde de la Municipalidad de Lima. "
        "Por los fuertes vientos, sujeta cada arbol con cuerdas desde una estaca "
        "a 36 cm del pie hasta un punto a 48 cm de altura en el tronco. "
        "¿Cuantos centimetros de cuerda comprara si tiene que sujetar 8 arboles "
        "con dos cuerdas cada uno?",
        3,
        "Calcula la longitud de cada cuerda con el teorema de Pitagoras: "
        "c = raiz(36^2 + 48^2). Luego multiplica por 2 cuerdas y por 8 arboles.",
        5,
        "960 cm",
        "120 cm",
        "60 cm",
        "672 cm",
    ),

    # ── Competencia 4: Gestion de datos e incertidumbre (id=4) ──────────────
    # Ficha 4, p.50-51, EJ3 - IMAGEN: grafico circular de color de ojos
    (
        "Un grafico circular muestra el color de ojos de 200 personas: ojos azules "
        "6 %, ojos verdes 4 %, ojos cafes 34 %, ojos negros 56 %. Respecto al "
        "grafico, se afirma: I. Hay 20 personas con ojos verdes o azules. "
        "II. 112 personas tienen ojos de color negro. "
        "III. 180 personas tienen ojos de color negro o cafe. "
        "¿Que afirmaciones son correctas?",
        4,
        "Calcula cada afirmacion: I) (6+4)% de 200; II) 56% de 200; "
        "III) (56+34)% de 200. Compara con los valores dados.",
        2,
        "I, II y III",
        "Solo I",
        "I y II",
        "I y III",
    ),
    # Ficha 8, p.94, EJ3 - IMAGEN: tabla de resultados de evaluacion
    (
        "La profesora Jennifer registra los resultados de las evaluaciones de sus "
        "estudiantes en la siguiente tabla: Inicio (0-10): 12 estudiantes; "
        "En proceso (11-13): 10 estudiantes; Satisfactorio (14-20): 8 estudiantes. "
        "Al elegir un estudiante del aula al azar, ¿cual es la probabilidad de que "
        "NO tenga un puntaje satisfactorio?",
        4,
        "Los que NO tienen puntaje satisfactorio estan en Inicio o En proceso. "
        "Suma esos estudiantes y divide entre el total.",
        3,
        "11/15",
        "4/15",
        "4/11",
        "8/30",
    ),
    # Ficha 8, p.94, EJ1 - IMAGEN: tabla de estudiantes por seccion y genero
    (
        "La profesora de Comunicacion organiza un debate entre las secciones A y B "
        "del 3.o de secundaria. Ella escribe los nombres en papelitos y los coloca "
        "en una urna. La seccion A tiene 16 varones y 12 mujeres; la seccion B "
        "tiene 9 varones y 15 mujeres. Al extraer un papelito al azar, ¿cual es "
        "la probabilidad de que contenga el nombre de un estudiante de la seccion A?",
        4,
        "Cuenta el total de estudiantes en la urna y cuantos son de la seccion A. "
        "P = estudiantes seccion A / total de estudiantes.",
        4,
        "7/13",
        "7/24",
        "12/28",
        "3/4",
    ),
    # Ficha 8, p.94, EJ8 - texto con tabla
    (
        "En una institucion educativa, el 45 % de los estudiantes practica futbol, "
        "el 30 % juega basquet y el 20 % practica ambos deportes. Si se elige un "
        "estudiante al azar, ¿cual es la probabilidad de que no juegue ni futbol "
        "ni basquet?",
        4,
        "Usa la formula de la union: P(A U B) = P(A) + P(B) - P(A ∩ B). "
        "Luego P(ninguno) = 1 - P(A U B).",
        5,
        "45 %",
        "30 %",
        "55 %",
        "70 %",
    ),
    # Ficha 8, p.94, EJ6 - texto puro, sin imagen
    (
        "Renato ahorra sus propinas semanales en una alcancia. Tiene 30 monedas "
        "en total: cinco son de S/ 1 y el resto son de S/ 2 y de S/ 5. Si la "
        "probabilidad de extraer al azar una moneda de S/ 2 es de 0,6, "
        "¿cuantas monedas de S/ 5 hay en la alcancia?",
        4,
        "Si P(S/2) = 0,6, entonces hay 0,6 x 30 = 18 monedas de S/2. "
        "El resto son de S/5: 30 - 5 - 18 = ?",
        6,
        "7 monedas",
        "5 monedas",
        "8 monedas",
        "10 monedas",
    ),
]


def main():
    print("Conectando a la base de datos...")
    conn = psycopg.connect(DATABASE_URL)
    cur = conn.cursor()

    try:
        print("Iniciando transaccion...")

        # 1. Insertar los nuevos ejercicios
        nuevos_ids = []
        for ej in EJERCICIOS:
            desc, id_comp, pista, nivel, op_a, op_b, op_c, op_d = ej
            cur.execute(
                """
                INSERT INTO ejercicios (descripcion, respuesta_correcta, id_competencia, pista, nivel_logro)
                VALUES (%s, 'A', %s, %s, %s)
                RETURNING id_ejercicio
                """,
                (desc, id_comp, pista, nivel),
            )
            id_ej = cur.fetchone()[0]
            nuevos_ids.append(id_ej)

            for letra, texto, es_corr in [
                ("A", op_a, True),
                ("B", op_b, False),
                ("C", op_c, False),
                ("D", op_d, False),
            ]:
                cur.execute(
                    """
                    INSERT INTO opciones_ejercicio (letra, descripcion, es_correcta, id_ejercicio)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (letra, texto, es_corr, id_ej),
                )

        print(f"  -> {len(nuevos_ids)} ejercicios nuevos preparados.")

        # 2. Solo si todo fue bien, borrar los anteriores
        cur.execute(
            "SELECT id_ejercicio FROM ejercicios WHERE id_ejercicio != ALL(%s)",
            (nuevos_ids,),
        )
        ids_viejos = [r[0] for r in cur.fetchall()]

        if ids_viejos:
            cur.execute(
                "DELETE FROM respuestas_estudiantes WHERE id_ejercicio = ANY(%s)",
                (ids_viejos,),
            )
            cur.execute(
                "DELETE FROM progreso WHERE id_ejercicio = ANY(%s)",
                (ids_viejos,),
            )
            cur.execute(
                "DELETE FROM recomendaciones WHERE id_ejercicio = ANY(%s)",
                (ids_viejos,),
            )
            cur.execute(
                "DELETE FROM opciones_ejercicio WHERE id_ejercicio = ANY(%s)",
                (ids_viejos,),
            )
            cur.execute(
                "DELETE FROM ejercicios WHERE id_ejercicio = ANY(%s)",
                (ids_viejos,),
            )
            print(f"  -> {len(ids_viejos)} ejercicios anteriores eliminados.")

        conn.commit()
        print("\nExito: 20 ejercicios MINEDU insertados correctamente.")
        print("IDs nuevos:", nuevos_ids)

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        print("La base de datos NO fue modificada (rollback aplicado).")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
