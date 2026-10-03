#!/usr/bin/env python3
"""Monitor de los dos finales de carrera de una valvula.

No acciona ninguna salida. Debe ejecutarse con caudal.service detenido para
evitar que dos procesos inicialicen simultaneamente el hardware del PLC.
"""

import argparse
import signal
import subprocess
import sys
import time

import librpiplc.rpiplc as PLC


MODELO_FAMILIA = "RPIPLC_V6"
MODELO_PLC = "RPIPLC_19R"
ENTRADA_ABIERTA = "I0.0"
ENTRADA_CERRADA = "I0.1"
SERVICIO_EXISTENTE = "caudal.service"

seguir = True


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


def main():
    parser = argparse.ArgumentParser(
        description="Monitorea I0.0 (abierta) e I0.1 (cerrada), sin accionar salidas."
    )
    parser.add_argument(
        "--equipo",
        choices=("vtork", "bray"),
        default="vtork",
        help="Solo cambia la etiqueta mostrada; el cableado es el mismo.",
    )
    parser.add_argument("--invertir-abierta", action="store_true")
    parser.add_argument("--invertir-cerrada", action="store_true")
    parser.add_argument(
        "--intervalo",
        type=float,
        default=0.20,
        help="Intervalo de lectura en segundos (minimo 0.05).",
    )
    args = parser.parse_args()

    if servicio_activo():
        print(
            f"ERROR: {SERVICIO_EXISTENTE} esta activo. Detenerlo antes de iniciar "
            "esta prueba para evitar acceso simultaneo al hardware.",
            file=sys.stderr,
        )
        return 2

    intervalo = max(0.05, args.intervalo)
    etiqueta = "Equipo 1 - Indave/V-Tork" if args.equipo == "vtork" else "Equipo 2 - Bray"

    signal.signal(signal.SIGINT, manejar_senal)
    signal.signal(signal.SIGTERM, manejar_senal)

    if not PLC.init(MODELO_FAMILIA, MODELO_PLC):
        print("ERROR: no se pudo inicializar el PLC.", file=sys.stderr)
        return 3

    try:
        PLC.pin_mode(ENTRADA_ABIERTA, PLC.INPUT)
        PLC.pin_mode(ENTRADA_CERRADA, PLC.INPUT)
        print(f"Monitoreando {etiqueta}. Ctrl+C para terminar.")
        print(f"Abierta={ENTRADA_ABIERTA}  Cerrada={ENTRADA_CERRADA}")

        anterior = None
        while seguir:
            abierta = bool(PLC.digital_read(ENTRADA_ABIERTA)) ^ args.invertir_abierta
            cerrada = bool(PLC.digital_read(ENTRADA_CERRADA)) ^ args.invertir_cerrada
            estado = interpretar(abierta, cerrada)
            actual = (abierta, cerrada, estado)
            if actual != anterior:
                marca = time.strftime("%Y-%m-%d %H:%M:%S")
                print(
                    f"{marca}  abierta={int(abierta)}  cerrada={int(cerrada)}  {estado}",
                    flush=True,
                )
                anterior = actual
            time.sleep(intervalo)
    finally:
        PLC.deinit()
        print("Monitor finalizado.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

