// Decode only buffer views stored in the pinned roster models; keep KTX2 intact.
import fs from 'node:fs';
import { MeshoptDecoder } from 'meshoptimizer';

const [, , input, jsonOutput, binOutput] = process.argv;
const glb = fs.readFileSync(input);
if (glb.toString('ascii', 0, 4) !== 'glTF' || glb.readUInt32LE(4) !== 2 ||
    glb.readUInt32LE(8) !== glb.length) throw new Error(`GLB inválido: ${input}`);
const jsonEnd = glb.readUInt32LE(12) + 20;
if (glb.toString('ascii', 16, 20) !== 'JSON' ||
    glb.toString('ascii', jsonEnd + 4, jsonEnd + 8) !== 'BIN\0') throw new Error('Se requieren bloques JSON/BIN');
const doc = JSON.parse(glb.toString('utf8', 20, jsonEnd));
const binary = glb.subarray(jsonEnd + 8);
function bytes(view) {
    const start = view.byteOffset ?? 0;
    const end = start + view.byteLength;
    if (view.buffer !== 0 || start < 0 || end > binary.length) throw new Error('Buffer view fuera del BIN');
    return binary.subarray(start, end);
}

await MeshoptDecoder.ready;
let offset = 0;
const chunks = [];
for (const view of doc.bufferViews) {
    const meshopt = view.extensions?.EXT_meshopt_compression;
    let data;
    if (meshopt) {
        if (meshopt.count * meshopt.byteStride !== view.byteLength) throw new Error('Tamaño Meshopt inválido');
        data = Buffer.alloc(view.byteLength);
        MeshoptDecoder.decodeGltfBuffer(data, meshopt.count, meshopt.byteStride,
            bytes(meshopt), meshopt.mode, meshopt.filter);
        delete view.extensions.EXT_meshopt_compression;
    } else {
        data = bytes(view);
    }
    view.byteOffset = offset;
    view.buffer = 0;
    chunks.push(data);
    const padding = (4 - data.length % 4) % 4;
    chunks.push(Buffer.alloc(padding));
    offset += data.length + padding;
}
doc.buffers = [{ byteLength: offset }];
fs.writeFileSync(jsonOutput, JSON.stringify(doc));
fs.writeFileSync(binOutput, Buffer.concat(chunks));
