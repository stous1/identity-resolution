// Puntúa pares con el motor de la demo: node puntuar_demo.mjs modelo.json pares.json
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const [modeloRuta, paresRuta] = process.argv.slice(2);
const motorUrl = pathToFileURL(resolve(import.meta.dirname, "../../docs/demo/motor.js"));
const { crearMotor } = await import(motorUrl.href);
const motor = crearMotor(JSON.parse(readFileSync(modeloRuta, "utf8")));
const pares = JSON.parse(readFileSync(paresRuta, "utf8"));
const salida = pares.map(([a, b]) => {
  const r = motor.comparar(a, b);
  return { gammas: Object.fromEntries(r.detalle.map((d) => [d.columna, d.gamma])), peso: r.peso };
});
process.stdout.write(JSON.stringify(salida));
