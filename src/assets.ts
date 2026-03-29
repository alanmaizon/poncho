import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

const TRACK_PATH = '/assets/models/racetrack_figure8.glb';
const CAR_PATH = '/assets/models/car.glb';
const TERRAIN_MARGIN = 180;
const TERRAIN_SEGMENTS_X = 140;
const TERRAIN_SEGMENTS_Z = 120;
const TERRAIN_SHOULDER_PAD = 12;
const TERRAIN_BLEND = 85;
const TERRAIN_BERM_HEIGHT = 2.6;
const TERRAIN_BERM_OFFSET = 22;
const TERRAIN_BERM_WIDTH = 18;
const TERRAIN_BASE_HEIGHT = -0.08;

export interface SpawnInfo {
  position: THREE.Vector3;
  heading: number;
}

export interface TrackObjects {
  track: THREE.Group;
  walls: THREE.Mesh[];
  roadMesh: THREE.Mesh | null;
  checkpoints: THREE.Mesh[];
  startLine: THREE.Mesh | null;
  spawn: SpawnInfo;
}

interface TerrainBounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

interface TerrainProfile {
  bounds: TerrainBounds;
  featureBounds: TerrainBounds;
  centerline: THREE.Vector2[];
  roadHalfWidth: number;
}

function enableShadows(obj: THREE.Object3D) {
  obj.traverse((child) => {
    if ((child as THREE.Mesh).isMesh) {
      child.castShadow = true;
      child.receiveShadow = true;
    }
  });
}

export async function loadAssets(scene: THREE.Scene) {
  const [trackObjects, carWrapper] = await Promise.all([loadTrack(), loadCar()]);

  scene.add(trackObjects.track);
  scene.add(carWrapper);

  carWrapper.position.copy(trackObjects.spawn.position);
  carWrapper.rotation.y = trackObjects.spawn.heading;

  return { ...trackObjects, car: carWrapper };
}

function loadTrack(): Promise<TrackObjects> {
  return new Promise((resolve, reject) => {
    const loader = new GLTFLoader();
    loader.load(
      TRACK_PATH,
      (gltf) => {
        const track = gltf.scene;

        const box = new THREE.Box3().setFromObject(track);
        track.position.y -= box.min.y;

        enableShadows(track);

        const extracted = extractTrackObjects(track);
        setSpaceTrackPresentation(track);
        addSpaceTrackFx(
          track,
          extracted.roadMesh,
          extracted.checkpoints,
          extracted.startLine
        );

        // Walls: invisible collision geometry
        for (const wall of extracted.walls) {
          wall.visible = false;
        }

        // Checkpoints & StartLine now double as visible space-track markers.
        for (const cp of extracted.checkpoints) {
          cp.visible = true;
          cp.castShadow = false;
          cp.receiveShadow = false;
        }
        if (extracted.startLine) {
          extracted.startLine.visible = true;
          extracted.startLine.castShadow = false;
          extracted.startLine.receiveShadow = false;
        }

        resolve({ track, ...extracted });
      },
      undefined,
      reject
    );
  });
}

interface ExtractedObjects {
  walls: THREE.Mesh[];
  roadMesh: THREE.Mesh | null;
  checkpoints: THREE.Mesh[];
  startLine: THREE.Mesh | null;
  spawn: SpawnInfo;
}

function extractTrackObjects(track: THREE.Object3D): ExtractedObjects {
  const walls: THREE.Mesh[] = [];
  const checkpoints: THREE.Mesh[] = [];
  let startLine: THREE.Mesh | null = null;
  let roadMesh: THREE.Mesh | null = null;
  let checkpoint01: THREE.Object3D | null = null;

  track.traverse((child) => {
    const mesh = child as THREE.Mesh;

    if (child.name === 'LeftWall' || child.name === 'RightWall') {
      if (mesh.isMesh) walls.push(mesh);
    }

    if (child.name === 'Road') {
      if (mesh.isMesh) roadMesh = mesh;
    }

    if (child.name.startsWith('Checkpoint_')) {
      if (mesh.isMesh) checkpoints.push(mesh);
      if (child.name === 'Checkpoint_01') checkpoint01 = child;
    }

    if (child.name === 'StartLine') {
      if (mesh.isMesh) startLine = mesh;
    }
  });

  checkpoints.sort((a, b) => a.name.localeCompare(b.name));

  const spawn = computeSpawn(startLine, checkpoint01);

  console.log(
    `Track loaded: ${walls.length} walls, road=${!!roadMesh}, ${checkpoints.length} checkpoints, startLine=${!!startLine}`
  );

  return { walls, roadMesh, checkpoints, startLine, spawn };
}

function setSpaceTrackPresentation(track: THREE.Object3D) {
  track.traverse((child) => {
    const mesh = child as THREE.Mesh;
    if (!mesh.isMesh) return;

    if (isEnvironmentNode(child.name)) {
      child.visible = false;
      child.castShadow = false;
      child.receiveShadow = false;
      return;
    }

    const materials = Array.isArray(mesh.material)
      ? mesh.material
      : [mesh.material];

    for (const material of materials) {
      if (!(material instanceof THREE.MeshStandardMaterial)) continue;

      if (child.name === 'Road') {
        material.color = new THREE.Color(0x101420);
        material.emissive = new THREE.Color(0x0a1630);
        material.emissiveIntensity = 0.45;
        material.roughness = 0.72;
        material.metalness = 0.22;
      } else if (child.name.startsWith('Curb')) {
        material.color.offsetHSL(0, 0, 0.02);
        material.emissive = new THREE.Color(0x220812);
        material.emissiveIntensity = 0.28;
        material.roughness = 0.45;
      } else if (child.name.startsWith('Stripe_')) {
        material.color = new THREE.Color(0xd8e6ff);
        material.emissive = new THREE.Color(0x7cb8ff);
        material.emissiveIntensity = 0.75;
        material.roughness = 0.3;
      } else if (child.name === 'BridgeDeck') {
        material.color = new THREE.Color(0x1a2030);
        material.emissive = new THREE.Color(0x050a16);
        material.emissiveIntensity = 0.35;
      } else if (child.name.startsWith('Checkpoint_')) {
        material.color = new THREE.Color(0x79c7ff);
        material.emissive = new THREE.Color(0x2fb8ff);
        material.emissiveIntensity = 2.2;
        material.transparent = true;
        material.opacity = 0.2;
        material.depthWrite = false;
        material.roughness = 0.1;
        material.metalness = 0.05;
      } else if (child.name === 'StartLine') {
        material.color = new THREE.Color(0xffd9f5);
        material.emissive = new THREE.Color(0xff3bbd);
        material.emissiveIntensity = 2.8;
        material.transparent = true;
        material.opacity = 0.9;
        material.depthWrite = false;
        material.roughness = 0.12;
        material.metalness = 0.05;
      }
    }
  });
}

function addSpaceTrackFx(
  track: THREE.Group,
  roadMesh: THREE.Mesh | null,
  checkpoints: THREE.Mesh[],
  startLine: THREE.Mesh | null
) {
  if (roadMesh) {
    const edgeLights = createEdgeLightRibbons(roadMesh);
    for (const light of edgeLights) {
      track.add(light);
    }
  }

  for (const checkpoint of checkpoints) {
    checkpoint.renderOrder = 4;
  }
  if (startLine) {
    startLine.renderOrder = 5;
  }
}

function computeSpawn(
  startLine: THREE.Object3D | null,
  checkpoint01: THREE.Object3D | null
): SpawnInfo {
  if (!startLine) {
    return { position: new THREE.Vector3(0, 0.1, 0), heading: Math.PI };
  }

  const startBox = new THREE.Box3().setFromObject(startLine);
  const startCenter = startBox.getCenter(new THREE.Vector3());

  let heading = Math.PI;
  if (checkpoint01) {
    const cp1Box = new THREE.Box3().setFromObject(checkpoint01);
    const cp1Center = cp1Box.getCenter(new THREE.Vector3());
    heading = Math.atan2(
      cp1Center.x - startCenter.x,
      cp1Center.z - startCenter.z
    );
  }

  // Keep spawn Y from the start line (may be elevated)
  startCenter.y += 0.1;
  return { position: startCenter, heading };
}

function extractRoadCenterline(
  roadMesh: THREE.Mesh,
  worldSpace = true
): THREE.Vector2[] {
  const positions = roadMesh.geometry.getAttribute('position');
  if (!positions || positions.count < 4 || positions.count % 2 !== 0) {
    return [];
  }

  const halfCount = positions.count / 2;
  const left = new THREE.Vector3();
  const right = new THREE.Vector3();
  const centerline: THREE.Vector2[] = [];

  for (let i = 0; i < halfCount; i++) {
    left.fromBufferAttribute(positions, i);
    right.fromBufferAttribute(positions, i + halfCount);
    if (worldSpace) {
      roadMesh.localToWorld(left);
      roadMesh.localToWorld(right);
    }

    centerline.push(
      new THREE.Vector2((left.x + right.x) * 0.5, (left.z + right.z) * 0.5)
    );
  }

  return centerline;
}

function createEdgeLightRibbons(roadMesh: THREE.Mesh) {
  const positions = roadMesh.geometry.getAttribute('position');
  if (!positions || positions.count < 4 || positions.count % 2 !== 0) {
    return [];
  }

  const halfCount = positions.count / 2;
  const leftEdge: THREE.Vector3[] = [];
  const rightEdge: THREE.Vector3[] = [];
  const left = new THREE.Vector3();
  const right = new THREE.Vector3();

  for (let i = 0; i < halfCount; i++) {
    left.fromBufferAttribute(positions, i);
    right.fromBufferAttribute(positions, i + halfCount);
    leftEdge.push(left.clone());
    rightEdge.push(right.clone());
  }

  return [
    buildEdgeLightRibbon(leftEdge, 1, 0x47d7ff, 0x0cb8ff, 'EdgeLightLeft'),
    buildEdgeLightRibbon(rightEdge, -1, 0xff5fcb, 0xff2d95, 'EdgeLightRight'),
  ];
}

function buildEdgeLightRibbon(
  edge: THREE.Vector3[],
  sideSign: number,
  colorHex: number,
  emissiveHex: number,
  name: string
) {
  const inner: THREE.Vector3[] = [];
  const outer: THREE.Vector3[] = [];

  for (let i = 0; i < edge.length; i++) {
    const point = edge[i];
    const tangent = edge[(i + 1) % edge.length]
      .clone()
      .sub(edge[(i - 1 + edge.length) % edge.length]);
    tangent.y = 0;
    tangent.normalize();

    const leftNormal = new THREE.Vector3(-tangent.z, 0, tangent.x).normalize();
    const offset = leftNormal.multiplyScalar(sideSign);
    const lift = new THREE.Vector3(0, 0.08, 0);
    inner.push(point.clone().addScaledVector(offset, 0.05).add(lift));
    outer.push(point.clone().addScaledVector(offset, 0.42).add(lift));
  }

  const geometry = new THREE.BufferGeometry();
  const verts = new Float32Array(edge.length * 2 * 3);
  const indices: number[] = [];

  for (let i = 0; i < edge.length; i++) {
    const i6 = i * 6;
    verts[i6] = inner[i].x;
    verts[i6 + 1] = inner[i].y;
    verts[i6 + 2] = inner[i].z;
    verts[i6 + 3] = outer[i].x;
    verts[i6 + 4] = outer[i].y;
    verts[i6 + 5] = outer[i].z;
  }

  for (let i = 0; i < edge.length; i++) {
    const a = i * 2;
    const b = a + 1;
    const c = ((i + 1) % edge.length) * 2;
    const d = c + 1;
    indices.push(a, b, d, a, d, c);
  }

  geometry.setAttribute('position', new THREE.BufferAttribute(verts, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();

  const mesh = new THREE.Mesh(
    geometry,
    new THREE.MeshStandardMaterial({
      color: colorHex,
      emissive: emissiveHex,
      emissiveIntensity: 2.4,
      roughness: 0.18,
      metalness: 0.08,
      toneMapped: true,
    })
  );
  mesh.name = name;
  mesh.castShadow = false;
  mesh.receiveShadow = false;
  mesh.renderOrder = 3;
  return mesh;
}

function isEnvironmentNode(name: string) {
  return (
    name === 'Ground' ||
    /^Tree_\d+/.test(name) ||
    /^Forest_\d+/.test(name) ||
    /^Bush_\d+/.test(name)
  );
}

function loadCar(): Promise<THREE.Group> {
  return new Promise((resolve, reject) => {
    const loader = new GLTFLoader();
    loader.load(
      CAR_PATH,
      (gltf) => {
        const car = gltf.scene;

        const box = new THREE.Box3().setFromObject(car);
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);
        if (maxDim > 0) {
          const targetLength = 8;
          const scale = targetLength / maxDim;
          car.scale.multiplyScalar(scale);
        }

        const centeredBox = new THREE.Box3().setFromObject(car);
        const center = centeredBox.getCenter(new THREE.Vector3());
        car.position.x -= center.x;
        car.position.z -= center.z;
        car.position.y -= centeredBox.min.y;

        car.rotation.y = Math.PI;

        const wrapper = new THREE.Group();
        wrapper.add(car);

        enableShadows(wrapper);
        resolve(wrapper);
      },
      undefined,
      reject
    );
  });
}
