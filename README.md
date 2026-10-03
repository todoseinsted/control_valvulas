# Control y prueba de válvulas neumáticas

Programas de prueba para dos conjuntos de válvula neumática conectados a un
Industrial Shields Raspberry PLC 19R:

- Conjunto Indave / V-Tork con electroválvula ASCO.
- Conjunto Bray con electroválvula Bray.

A nivel de programación ambos equipos se manejan de la misma manera. La
opción `--equipo` solamente identifica el conjunto en pantalla y en el nombre
del registro; no cambia la lógica de control.

## Señales utilizadas

| Canal | Función |
| --- | --- |
| `R0.4` | Mando de la electroválvula de 24 VCC mediante el relé del PLC |
| `I0.0` | Confirmación de válvula abierta |
| `I0.1` | Confirmación de válvula cerrada |

Los contactos de posición pertenecen a la caja de finales de carrera del
actuador y son independientes de la bobina de la electroválvula.

## Programas

### `monitor_finales_carrera.py`

Lee `I0.0` e `I0.1` sin accionar ninguna salida. Informa uno de estos estados:

- `ABIERTA`: solamente está activo el final de carrera de apertura.
- `CERRADA`: solamente está activo el final de carrera de cierre.
- `EN_TRANSITO_O_SIN_SENAL`: ninguno está activo.
- `FALLA_DOBLE_SENAL`: los dos están activos simultáneamente.

### `prueba_actuador_neumatico.py`

Ejecuta una prueba para un actuador de simple efecto configurado como
*fail-close*:

1. `R0.4` desenergizado: debe confirmar `CERRADA`.
2. `R0.4` energizado: debe confirmar `ABIERTA`.
3. `R0.4` desenergizado nuevamente: debe regresar a `CERRADA`.

Cada fase dura tres segundos por defecto. La salida se fuerza a OFF al iniciar,
al finalizar, ante `Ctrl+C` y ante la terminación del proceso. Cada prueba crea
un archivo CSV en `/home/nferraro/Ensayos/logs_prueba_valvulas/`.

## Seguridad

Realizar las pruebas únicamente en banco, fuera de proceso y de atmósferas
peligrosas. Utilizar aire limpio regulado, mantener personas y herramientas
fuera de la zona de movimiento y confirmar en la placa que la bobina instalada
sea realmente de 24 VCC.

El software no reemplaza los enclavamientos cableados, protecciones eléctricas
ni una parada de emergencia. No aflojar conexiones neumáticas mientras exista
presión. Antes de energizar, verificar que la alimentación de 24 VCC llegue a
la bobina a través del contacto de relé correspondiente y no directamente desde
una salida electrónica no apta para su corriente.

## Instalación en el PLC

Copiar los dos archivos Python a:

```text
/home/nferraro/Ensayos/
```

Los programas usan la biblioteca `librpiplc`, instalada en el PLC Industrial
Shields.

No deben ejecutarse mientras `caudal.service` esté activo porque ambos procesos
intentarían inicializar el mismo hardware. Detenerlo antes de la prueba:

```bash
sudo systemctl stop caudal.service
cd /home/nferraro/Ensayos
```

## Uso

Primero comprobar los finales de carrera sin mover la válvula:

```bash
python3 monitor_finales_carrera.py --equipo vtork
```

Para el conjunto Bray:

```bash
python3 monitor_finales_carrera.py --equipo bray
```

Si una entrada entrega la lógica eléctrica opuesta, se puede invertir durante
la prueba:

```bash
python3 monitor_finales_carrera.py --equipo vtork --invertir-abierta
```

Después de verificar las posiciones, ejecutar un ciclo automático:

```bash
python3 prueba_actuador_neumatico.py --equipo vtork --confirmo-prueba-segura
```

o:

```bash
python3 prueba_actuador_neumatico.py --equipo bray --confirmo-prueba-segura
```

La confirmación escrita es obligatoria para impedir movimientos accidentales.
Las duraciones pueden ajustarse entre 0,5 y 10 segundos:

```bash
python3 prueba_actuador_neumatico.py \
  --equipo vtork \
  --tiempo-reposo 4 \
  --tiempo-energizado 5 \
  --confirmo-prueba-segura
```

Al terminar:

```bash
sudo systemctl start caudal.service
```

## Interpretación del resultado

Una prueba correcta muestra:

```text
Reposo inicial: CERRADA
Energizada:     ABIERTA
Reposo final:   CERRADA
RESULTADO: secuencia fail-close correcta.
```

Si falla, revisar el cableado de los contactos COM/NO/NC, el ajuste de las
levas de los finales de carrera, la presión de aire, la tensión de la bobina y
el sentido configurado del actuador.

