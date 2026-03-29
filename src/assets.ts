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
        removeFigure8InteriorScenery(track, extracted.roadMesh);
        const terrain = createFigure8Terrain(extracted.roadMesh);
        if (terrain) {
          hideTrackGround(track);
          alignSceneryToTerrain(track, terrain.profile);
          track.add(terrain.mesh);
        }

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

function removeFigure8InteriorScenery(
  track: THREE.Object3D,
  roadMesh: THREE.Mesh | null
) {
  if (!roadMesh) return;

  track.updateMatrixWorld(true);

  const centerline = extractRoadCenterline(roadMesh);
  if (centerline.length < 3) return;

  const scenery = collectSceneryInstances(track);
  let removedCount = 0;

  for (const instance of scenery.values()) {
    if (windingNumber(instance.anchor, centerline) === 0) continue;

    for (const object of instance.objects) {
      object.parent?.remove(object);
    }
    removedCount += 1;
  }

  if (removedCount > 0) {
    console.log(`Removed ${removedCount} scenery instances from inside the figure-8 footprint`);
  }
}

function createFigure8Terrain(roadMesh: THREE.Mesh | null) {
  if (!roadMesh) return null;

  const centerline = extractRoadCenterline(roadMesh, false);
  if (centerline.length < 3) return null;

  const profile: TerrainProfile = {
    bounds: computeTerrainBounds(centerline, TERRAIN_MARGIN),
    featureBounds: computeTerrainBounds(centerline, 0),
    centerline,
    roadHalfWidth: estimateRoadHalfWidth(roadMesh),
  };

  const vertexCount = (TERRAIN_SEGMENTS_X + 1) * (TERRAIN_SEGMENTS_Z + 1);
  const positions = new Float32Array(vertexCount * 3);
  const colors = new Float32Array(vertexCount * 3);
  const indices: number[] = [];
  const color = new THREE.Color();
  const meadow = new THREE.Color(0x65863f);
  const hill = new THREE.Color(0x90a461);
  const dirt = new THREE.Color(0x8d7a58);

  const width = profile.bounds.maxX - profile.bounds.minX;
  const depth = profile.bounds.maxY - profile.bounds.minY;

  let vertexIndex = 0;
  for (let iz = 0; iz <= TERRAIN_SEGMENTS_Z; iz++) {
    const z = profile.bounds.minY + (iz / TERRAIN_SEGMENTS_Z) * depth;

    for (let ix = 0; ix <= TERRAIN_SEGMENTS_X; ix++) {
      const x = profile.bounds.minX + (ix / TERRAIN_SEGMENTS_X) * width;
      const point = new THREE.Vector2(x, z);
      const roadDist = distanceToClosedPolyline(point, profile.centerline);
      const corridor = smoothstep(
        profile.roadHalfWidth + TERRAIN_SHOULDER_PAD,
        profile.roadHalfWidth + TERRAIN_SHOULDER_PAD + TERRAIN_BLEND,
        roadDist
      );
      const height = sampleTerrainHeight(point, profile, roadDist, corridor);

      const i3 = vertexIndex * 3;
      positions[i3] = x;
      positions[i3 + 1] = height;
      positions[i3 + 2] = z;

      color.lerpColors(meadow, hill, THREE.MathUtils.clamp((height + 1.5) / 16, 0, 1));
      color.lerp(dirt, (1 - corridor) * 0.35);
      colors[i3] = color.r;
      colors[i3 + 1] = color.g;
      colors[i3 + 2] = color.b;
      vertexIndex += 1;
    }
  }

  const stride = TERRAIN_SEGMENTS_X + 1;
  for (let iz = 0; iz < TERRAIN_SEGMENTS_Z; iz++) {
    for (let ix = 0; ix < TERRAIN_SEGMENTS_X; ix++) {
      const a = iz * stride + ix;
      const b = a + 1;
      const d = (iz + 1) * stride + ix;
      const c = d + 1;
      indices.push(a, b, c, a, c, d);
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();

  const mesh = new THREE.Mesh(
    geometry,
    new THREE.MeshStandardMaterial({
      vertexColors: true,
      roughness: 1,
      metalness: 0,
    })
  );
  mesh.name = 'RuntimeTerrain';
  mesh.receiveShadow = true;

  return { mesh, profile };
}

function hideTrackGround(track: THREE.Object3D) {
  const ground = track.getObjectByName('Ground');
  if (ground) {
    ground.visible = false;
  }
}

function alignSceneryToTerrain(track: THREE.Object3D, profile: TerrainProfile) {
  track.updateMatrixWorld(true);

  for (const instance of collectSceneryInstances(track, false).values()) {
    const targetY = sampleTerrainHeight(instance.anchor, profile);
    const delta = targetY - instance.baseY;
    if (Math.abs(delta) < 0.01) continue;

    for (const object of instance.objects) {
      object.position.y += delta;
    }
  }
}

function computeTerrainBounds(centerline: THREE.Vector2[], margin: number): TerrainBounds {
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;

  for (const point of centerline) {
    minX = Math.min(minX, point.x);
    maxX = Math.max(maxX, point.x);
    minY = Math.min(minY, point.y);
    maxY = Math.max(maxY, point.y);
  }

  return {
    minX: minX - margin,
    maxX: maxX + margin,
    minY: minY - margin,
    maxY: maxY + margin,
  };
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

interface SceneryInstance {
  anchor: THREE.Vector2;
  baseY: number;
  objects: THREE.Object3D[];
}

function collectSceneryInstances(track: THREE.Object3D, worldSpace = true) {
  const grouped = new Map<
    string,
    { sum: THREE.Vector2; count: number; baseY: number; objects: THREE.Object3D[] }
  >();

  track.traverse((child) => {
    const key = getSceneryInstanceKey(child.name);
    if (!key) return;

    const worldPos = child.getWorldPosition(new THREE.Vector3());
    const pos = worldSpace ? worldPos : track.worldToLocal(worldPos.clone());
    const entry =
      grouped.get(key) ??
      { sum: new THREE.Vector2(), count: 0, baseY: Infinity, objects: [] };

    entry.sum.add(new THREE.Vector2(pos.x, pos.z));
    entry.count += 1;
    entry.baseY = Math.min(entry.baseY, pos.y);
    entry.objects.push(child);
    grouped.set(key, entry);
  });

  return new Map(
    Array.from(grouped.entries()).map(([key, value]) => [
      key,
      {
        anchor: value.sum.multiplyScalar(1 / value.count),
        baseY: value.baseY,
        objects: value.objects,
      } satisfies SceneryInstance,
    ])
  );
}

function getSceneryInstanceKey(name: string) {
  const match = name.match(/^(Tree|Forest|Bush)_\d+/);
  return match ? match[0] : null;
}

function windingNumber(point: THREE.Vector2, polygon: THREE.Vector2[]) {
  let winding = 0;

  for (let i = 0; i < polygon.length; i++) {
    const a = polygon[i];
    const b = polygon[(i + 1) % polygon.length];

    if (a.y <= point.y) {
      if (b.y > point.y && signedArea(a, b, point) > 0) winding += 1;
    } else if (b.y <= point.y && signedArea(a, b, point) < 0) {
      winding -= 1;
    }
  }

  return winding;
}

function signedArea(a: THREE.Vector2, b: THREE.Vector2, point: THREE.Vector2) {
  return (b.x - a.x) * (point.y - a.y) - (point.x - a.x) * (b.y - a.y);
}

function distanceToClosedPolyline(point: THREE.Vector2, polyline: THREE.Vector2[]) {
  let best = Infinity;

  for (let i = 0; i < polyline.length; i++) {
    const a = polyline[i];
    const b = polyline[(i + 1) % polyline.length];
    best = Math.min(best, distanceToSegment(point, a, b));
  }

  return best;
}

function distanceToSegment(
  point: THREE.Vector2,
  a: THREE.Vector2,
  b: THREE.Vector2
) {
  const ab = new THREE.Vector2().subVectors(b, a);
  const denom = ab.lengthSq();
  if (denom === 0) return point.distanceTo(a);

  const t = THREE.MathUtils.clamp(
    new THREE.Vector2().subVectors(point, a).dot(ab) / denom,
    0,
    1
  );

  return point.distanceTo(new THREE.Vector2().copy(a).addScaledVector(ab, t));
}

function smoothstep(edge0: number, edge1: number, value: number) {
  if (edge0 === edge1) return value < edge0 ? 0 : 1;
  const t = THREE.MathUtils.clamp((value - edge0) / (edge1 - edge0), 0, 1);
  return t * t * (3 - 2 * t);
}

function sampleTerrainHeight(
  point: THREE.Vector2,
  profile: TerrainProfile,
  roadDist = distanceToClosedPolyline(point, profile.centerline),
  corridor = smoothstep(
    profile.roadHalfWidth + TERRAIN_SHOULDER_PAD,
    profile.roadHalfWidth + TERRAIN_SHOULDER_PAD + TERRAIN_BLEND,
    roadDist
  )
) {
  const { minX, maxX, minY, maxY } = profile.featureBounds;
  const spanX = maxX - minX;
  const spanY = maxY - minY;
  const maxSpan = Math.max(spanX, spanY);
  const infield = windingNumber(point, profile.centerline) !== 0 ? 1 : 0;
  const terrainStrength = corridor * 0.55 + corridor * corridor * 0.45;

  const waves =
    1.6 * Math.sin(point.x * 0.0085) +
    1.3 * Math.cos(point.y * 0.0065) +
    0.8 * Math.sin((point.x + point.y) * 0.0048);

  const infieldRoll =
    infield *
    (1.2 * Math.sin(point.x * 0.011) * Math.cos(point.y * 0.0105));

  const hillSpecs: Array<[number, number, number, number]> = [
    [minX - 140, maxY + 110, 8, maxSpan * 0.2],
    [maxX + 120, maxY + 70, 6, maxSpan * 0.18],
    [maxX + 150, minY - 100, 7, maxSpan * 0.22],
    [minX - 130, minY - 80, 7, maxSpan * 0.2],
    [(minX + maxX) * 0.5, minY - 150, 4, maxSpan * 0.24],
  ];

  let hills = 0;
  for (const [x, y, height, radius] of hillSpecs) {
    const distSq = (point.x - x) ** 2 + (point.y - y) ** 2;
    hills += height * Math.exp(-distSq / (radius * radius));
  }

  const basin =
    -1.2 *
    Math.exp(
      -(
        point.x * point.x +
        (point.y * 0.85) * (point.y * 0.85)
      ) /
        ((maxSpan * 0.22) ** 2)
    );

  const berm =
    TERRAIN_BERM_HEIGHT *
    Math.exp(
      -(
        (
          (roadDist -
            (profile.roadHalfWidth + TERRAIN_SHOULDER_PAD + TERRAIN_BERM_OFFSET)) /
          TERRAIN_BERM_WIDTH
        ) ** 2
      )
    );

  const shoulder =
    -0.2 *
    Math.exp(
      -(
        (
          (roadDist - (profile.roadHalfWidth + TERRAIN_SHOULDER_PAD) * 0.9) / 7
        ) ** 2
      )
    );

  return (
    TERRAIN_BASE_HEIGHT +
    shoulder +
    berm * (0.2 + 0.8 * corridor) +
    (waves + hills + basin + infieldRoll) * terrainStrength
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
