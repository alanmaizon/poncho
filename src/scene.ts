import * as THREE from 'three';

export function initRenderer() {
  const scene = new THREE.Scene();

  scene.background = new THREE.Color(0x030712);

  const camera = new THREE.PerspectiveCamera(
    55,
    window.innerWidth / window.innerHeight,
    0.3,
    2000
  );
  camera.position.set(0, 10, 20);

  // --- Renderer ---
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    powerPreference: 'high-performance',
  });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  document.body.appendChild(renderer.domElement);

  addSpaceBackdrop(scene);

  const ambient = new THREE.AmbientLight(0x88a4ff, 0.2);
  scene.add(ambient);

  const hemi = new THREE.HemisphereLight(0x4c6dff, 0x050814, 0.35);
  scene.add(hemi);

  const sun = new THREE.DirectionalLight(0xf5f7ff, 2.4);
  sun.position.set(80, 110, 30);
  sun.castShadow = true;
  sun.shadow.mapSize.set(4096, 4096);
  sun.shadow.camera.left = -150;
  sun.shadow.camera.right = 150;
  sun.shadow.camera.top = 150;
  sun.shadow.camera.bottom = -150;
  sun.shadow.camera.near = 1;
  sun.shadow.camera.far = 500;
  sun.shadow.bias = -0.00015;
  sun.shadow.normalBias = 0.01;
  scene.add(sun);

  const fill = new THREE.DirectionalLight(0x37d6ff, 0.7);
  fill.position.set(-45, 24, -65);
  scene.add(fill);

  const rim = new THREE.PointLight(0x8e64ff, 45, 420, 2);
  rim.position.set(-120, 45, -160);
  scene.add(rim);

  // Resize handling
  window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  return { scene, renderer, camera, sun };
}

function addSpaceBackdrop(scene: THREE.Scene) {
  const stars = new THREE.BufferGeometry();
  const starCount = 3500;
  const positions = new Float32Array(starCount * 3);
  const colors = new Float32Array(starCount * 3);
  const color = new THREE.Color();

  for (let i = 0; i < starCount; i++) {
    const radius = 900 + Math.random() * 700;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(THREE.MathUtils.randFloatSpread(2));
    const i3 = i * 3;

    positions[i3] = radius * Math.sin(phi) * Math.cos(theta);
    positions[i3 + 1] = radius * Math.cos(phi);
    positions[i3 + 2] = radius * Math.sin(phi) * Math.sin(theta);

    color.setHSL(0.55 + Math.random() * 0.12, 0.45, 0.7 + Math.random() * 0.25);
    colors[i3] = color.r;
    colors[i3 + 1] = color.g;
    colors[i3 + 2] = color.b;
  }

  stars.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  stars.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  scene.add(
    new THREE.Points(
      stars,
      new THREE.PointsMaterial({
        size: 2.1,
        sizeAttenuation: true,
        vertexColors: true,
        transparent: true,
        opacity: 0.95,
        depthWrite: false,
      })
    )
  );

  const planet = new THREE.Mesh(
    new THREE.SphereGeometry(78, 48, 48),
    new THREE.MeshStandardMaterial({
      color: 0x263455,
      emissive: 0x0b1026,
      emissiveIntensity: 0.5,
      roughness: 0.95,
      metalness: 0.02,
    })
  );
  planet.position.set(-310, 170, -560);
  scene.add(planet);

  const ring = new THREE.Mesh(
    new THREE.RingGeometry(110, 150, 96),
    new THREE.MeshBasicMaterial({
      color: 0x5ec8ff,
      transparent: true,
      opacity: 0.18,
      side: THREE.DoubleSide,
      depthWrite: false,
    })
  );
  ring.position.copy(planet.position);
  ring.rotation.x = Math.PI * 0.42;
  ring.rotation.y = Math.PI * 0.18;
  scene.add(ring);

  const nebula = new THREE.Mesh(
    new THREE.SphereGeometry(1400, 32, 24),
    new THREE.MeshBasicMaterial({
      color: 0x101a35,
      side: THREE.BackSide,
      transparent: true,
      opacity: 0.9,
      depthWrite: false,
    })
  );
  scene.add(nebula);
}
