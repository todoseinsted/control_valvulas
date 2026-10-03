#!/usr/bin/env python3
"""Prueba temporizada de un actuador neumatico de simple efecto.

La salida R0.4 comienza y termina desenergizada. El programa exige una
confirmacion explicita y limita a 10 segundos cada fase de la prueba.
"""

import argparse
import csv
import os
import signal
import subprocess
import sys
import time

import librpiplc.rpiplc as PLC


MODELO_FAMILIA = "RPIPLC_V6"
MODELO_PLC = "RPIPLC_19R"
ENTRADA_ABIERTA = "I0.0"
ENTRADA_CERRADA = "I0.1"
SALIDA_SOLENOIDE = "R0.4"
SERVICIO_EXISTENTE = "caudal.service"
DIRECTORIO_LOGS = "/home/nferraro/Ensayos/logs_prueba_valvulas"
TIEMPO_MAXIMO_FASE = 10.0

seguir = True
plc_inicializado = False


def manejar_senal(_signum, _frame):
    global seguir
    seguir = False


def servicio_activo():
    resultado = subprocess.run(
        ["systemctl", "is-active", "--quiet", SERVICIO_EXISTENTE],
        check=False,
    )
    return resultado.returncode == 0


def interpretar(abierta, cerrada):
    if abierta and not cerrada:
        return "ABIERTA"
    if cerrada and not abierta:
        return "CERRADA"
    if not abierta and not cerrada:
        return "EN_TRANSITO_O_SIN_SENAL"
    return "FALLA_DOBLE_SENAL"


def leer_entradas(args):
    abierta = bool(PLC.digital_read(ENTRADA_ABIERTA)) ^ args.invertir_abierta
    cerrada = bool(PLC.digital_read(ENTRADA_CERRADA)) ^ args.invertir_cerrada
    return abierta, cerrada, interpretar(abierta, cerrada)


def esperar_fase(nombre, duracion, energizada, args, escritor):
    PLC.digital_write(SALIDA_SOLENOIDE, PLC.HIGH if energizada else PLC.LOW)
    inicio = time.monotonic()
    anterior = None
    ultimo = (False, False, "SIN_LECTURA")

    while seguir and time.monotonic() - inicio < duracion:
        abierta, cerrada, estado = leer_entradas(args)
        ultimo = (abierta, cerrada, estado)
        transcurrido = time.monotonic() - inicio
        escritor.writerow(
            [
                time.strftime("%Y-%m-%d %H:%M:%S"),
                nombre,
                f"{transcurrido:.3f}",
                int(energizada),
                int(abierta),
                int(cerrada),
                estado,
            ]
        )
        actual = (abierta, cerrada, estado)
        if actual != anterior:
            print(
                f"{nombre:18s} t={transcurrido:5.2f}s  "
                f"abierta={int(abierta)} cerrada={int(cerrada)}  {estado}",
                flush=True,
            )
            anterior = actual
        time.sleep(0.10)

    return ultimo


def main():
    global plc_inicializado

    parser = argparse.ArgumentParser(
        description=(
            "Prueba una valvula fail-close: reposo, R0.4 energizado y retorno a reposo."
        )
    )
    parser.add_argument(
        "--equipo",
        choices=("vtork", "bray"),
        required=True,
        help="Identifica el equipo conectado; ambos usan los mismos canales.",
    )
    parser.add_argument(
        "--confirmo-prueba-segura",
        action="store_true",
        help="Confirma banco aislado, aire regulado y personal alejado del movimiento.",
    )
    parser.add_argument("--invertir-abierta", action="store_true")
    parser.add_argument("--invertir-cerrada", action="store_true")
    parser.add_argument("--tiempo-reposo", type=float, default=3.0)
    parser.add_argument("--tiempo-energizado", type=float, default=3.0)
    args = parser.parse_args()

    if not args.confirmo_prueba_segura:
        print(
            "ERROR: falta --confirmo-prueba-segura. No se acciono ninguna salida.",
            file=sys.stderr,
        )
        return 2

    if servicio_activo():
        print(
            f"ERROR: {SERVICIO_EXISTENTE} esta activo. Detenerlo antes de la prueba.",
            file=sys.stderr,
        )
        return 3

    for nombre, valor in (
        ("--tiempo-reposo", args.tiempo_reposo),
        ("--tiempo-energizado", args.tiempo_energizado),
    ):
        if not 0.5 <= valor <= TIEMPO_MAXIMO_FASE:
            print(f"ERROR: {nombre} debe estar entre 0.5 y 10 segundos.", file=sys.stderr)
            return 4

    etiqueta = "Equipo 1 - Indave/V-Tork" if args.equipo == "vtork" else "Equipo 2 - Bray"
    os.makedirs(DIRECTORIO_LOGS, exist_ok=True)
    marca_archivo = time.strftime("%Y%m%d_%H%M%S")
    ruta_log = os.path.join(DIRECTORIO_LOGS, f"prueba_{args.equipo}_{marca_archivo}.csv")

    signal.signal(signal.SIGINT, manejar_senal)
    signal.signal(signal.SIGTERM, manejar_senal)

    try:
        if not PLC.init(MODELO_FAMILIA, MODELO_PLC):
            print("ERROR: no se pudo inicializar el PLC.", file=sys.stderr)
            return 5
        plc_inicializado = True
        PLC.pin_mode(ENTRADA_ABIERTA, PLC.INPUT)
        PLC.pin_mode(ENTRADA_CERRADA, PLC.INPUT)
        PLC.pin_mode(SALIDA_SOLENOIDE, PLC.OUTPUT)
        PLC.digital_write(SALIDA_SOLENOIDE, PLC.LOW)

        print(f"Iniciando prueba de {etiqueta}")
        print(
            f"Solenoide={SALIDA_SOLENOIDE}, abierta={ENTRADA_ABIERTA}, "
            f"cerrada={ENTRADA_CERRADA}"
        )

        with open(ruta_log, "w", newline="", encoding="utf-8") as archivo:
            escritor = csv.writer(archivo)
            escritor.writerow(
                [
                    "timestamp",
                    "fase",
                    "segundos",
                    "solenoide",
                    "abierta",
                    "cerrada",
                    "estado",
                ]
            )
            reposo_inicial = esperar_fase(
                "REPOSO_INICIAL", args.tiempo_reposo, False, args, escritor
            )
            if seguir:
                energizada = esperar_fase(
                    "ENERGIZADA", args.tiempo_energizado, True, args, escritor
                )
            else:
                energizada = (False, False, "INTERRUMPIDA")
            PLC.digital_write(SALIDA_SOLENOIDE, PLC.LOW)
            if seguir:
                reposo_final = esperar_fase(
                    "REPOSO_FINAL", args.tiempo_reposo, False, args, escritor
                )
            else:
                reposo_final = (False, False, "INTERRUMPIDA")

        print("Resumen:")
        print(f"  Reposo inicial: {reposo_inicial[2]}")
        print(f"  Energizada:     {energizada[2]}")
        print(f"  Reposo final:   {reposo_final[2]}")
        print(f"  Registro:       {ruta_log}")

        correcta = (
            reposo_inicial[2] == "CERRADA"
            and energizada[2] == "ABIERTA"
            and reposo_final[2] == "CERRADA"
        )
        if correcta:
            print("RESULTADO: secuencia fail-close correcta.")
            return 0

        print("RESULTADO: revisar cableado, ajuste de levas, aire o sentido del actuador.")
        return 6
    finally:
        if plc_inicializado:
            try:
                PLC.digital_write(SALIDA_SOLENOIDE, PLC.LOW)
            finally:
                PLC.deinit()
        print("Salida R0.4 desenergizada. Prueba finalizada.")


if __name__ == "__main__":
    raise SystemExit(main())

