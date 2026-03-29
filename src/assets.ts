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

        // Walls: invisible collision geometry
        for (const wall of extracted.walls) {
          wall.visible = false;
        }

        // Checkpoints & StartLine: invisible triggers
        for (const cp of extracted.checkpoints) {
          cp.visible = false;
        }
        if (extracted.startLine) {
          extracted.startLine.visible = false;
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
      }
    }
  });
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

function estimateRoadHalfWidth(roadMesh: THREE.Mesh) {
  const positions = roadMesh.geometry.getAttribute('position');
  if (!positions || positions.count < 4 || positions.count % 2 !== 0) {
    return 7;
  }

  const halfCount = positions.count / 2;
  const left = new THREE.Vector3();
  const right = new THREE.Vector3();
  let total = 0;

  for (let i = 0; i < halfCount; i++) {
    left.fromBufferAttribute(positions, i);
    right.fromBufferAttribute(positions, i + halfCount);
    total += left.distanceTo(right) * 0.5;
  }

  return total / halfCount;
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
