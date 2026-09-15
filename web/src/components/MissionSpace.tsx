"use client";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

type View = "mission" | "terminal-a" | "terminal-b";

export default function MissionSpace({ connected, acquiring, disturbed, ground, view }: { connected: boolean; acquiring: boolean; disturbed: boolean; ground: boolean; view: View }) {
  return <Canvas dpr={[1, 2]} camera={{ position: [0, 6.5, 18], fov: 43 }} gl={{ antialias: true }}>
    <color attach="background" args={["#020817"]} />
    <fog attach="fog" args={["#020817", 16, 42]} />
    <ambientLight intensity={.32} />
    <directionalLight position={[7, 10, 7]} intensity={1.5} color="#a9d6ff" />
    <pointLight position={[0, 1, 0]} intensity={2} color="#3159ff" />
    <CameraRig view={view} />
    <Starfield />
    <OrbitPath />
    <EndpointSystem side="a" disturbed={disturbed} />
    {ground ? <GroundStation /> : <EndpointSystem side="b" disturbed={disturbed} />}
    {(connected || acquiring) && <OpticalLink ground={ground} disturbed={disturbed} acquiring={acquiring} />}
    <gridHelper args={[42, 42, "#17355e", "#0c1d3d"]} position={[0, -5, 0]} />
  </Canvas>;
}

function CameraRig({ view }: { view: View }) {
  const { camera } = useThree();
  const target = useRef(new THREE.Vector3());
  useFrame((_, dt) => {
    const presets: Record<View, [number, number, number]> = { mission: [0, 6.5, 18], "terminal-a": [-8, 3, 9], "terminal-b": [8, 3, 9] };
    const p = presets[view];
    camera.position.lerp(new THREE.Vector3(...p), 1 - Math.exp(-dt * 2.2));
    target.current.lerp(new THREE.Vector3(0, 0, 0), 1 - Math.exp(-dt * 2.2));
    camera.lookAt(target.current);
  });
  return null;
}

function Starfield() {
  const positions = useMemo(() => {
    const a = new Float32Array(900);
    for (let i = 0; i < a.length; i += 3) { const n = i / 3; a[i] = ((n * 79) % 59 - 29) * .65; a[i + 1] = ((n * 47) % 43 - 21) * .5; a[i + 2] = -8 - ((n * 31) % 50) * .45; }
    return a;
  }, []);
  return <points><bufferGeometry><bufferAttribute attach="attributes-position" args={[positions, 3]} /></bufferGeometry><pointsMaterial size={.035} color="#b9ddff" sizeAttenuation transparent opacity={.85} /></points>;
}

function OrbitPath() {
  const points = useMemo(() => Array.from({ length: 101 }, (_, i) => { const t = i / 100 * Math.PI * 2; return new THREE.Vector3(Math.cos(t) * 10, Math.sin(t) * 2.2 - 1, Math.sin(t) * 1.5); }), []);
  const geometry = useMemo(() => new THREE.BufferGeometry().setFromPoints(points), [points]);
  const line = useMemo(() => new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: "#1763bb", transparent: true, opacity: .65 })), [geometry]);
  return <primitive object={line} />;
}

function EndpointSystem({ side, disturbed }: { side: "a" | "b"; disturbed: boolean }) {
  const group = useRef<THREE.Group>(null); const x = side === "a" ? -6.1 : 6.1;
  useFrame(({ clock }) => { if (!group.current) return; const t = clock.getElapsedTime(); group.current.position.set(x + Math.sin(t * .42 + (side === "a" ? 0 : 2)) * .8, Math.sin(t * .42 + (side === "a" ? 0 : 2)) * 1.8, Math.cos(t * .42) * 1.15); group.current.rotation.y = t * .12; if (disturbed) { group.current.rotation.z = Math.sin(t * 13) * .035; group.current.rotation.x = Math.cos(t * 17) * .025; } });
  return <group ref={group}><Satellite /><Beacon /></group>;
}

function Satellite() {
  return <group><mesh castShadow><boxGeometry args={[2.3, 1.15, 1.25]} /><meshStandardMaterial color="#8fa8c3" metalness={.85} roughness={.25} /></mesh><mesh position={[1.28, 0, 0]} rotation={[0, 0, Math.PI / 2]}><cylinderGeometry args={[.42, .42, .8, 18]} /><meshStandardMaterial color="#d9e6f5" metalness={.9} /></mesh><mesh position={[1.72, 0, 0]} rotation={[0, 0, Math.PI / 2]}><cylinderGeometry args={[.16, .42, .55, 18]} /><meshStandardMaterial color="#18233d" metalness={.9} /></mesh><SolarPanel x={-3.25} /><SolarPanel x={3.25} /><mesh position={[0, .7, .08]}><boxGeometry args={[.7, .25, .22]} /><meshStandardMaterial color="#1d4e87" emissive="#103e8a" emissiveIntensity={.6} /></mesh></group>;
}
function SolarPanel({ x }: { x: number }) { return <group position={[x, 0, 0]}><mesh><boxGeometry args={[3.8, .95, .08]} /><meshStandardMaterial color="#123a7a" metalness={.7} roughness={.3} emissive="#0b2f75" emissiveIntensity={.55} /></mesh><mesh position={[x > 0 ? -1.95 : 1.95, 0, 0]}><boxGeometry args={[.25, .12, .12]} /><meshStandardMaterial color="#8da5c1" metalness={.8} /></mesh></group> }
function Beacon() { const light = useRef<THREE.PointLight>(null); useFrame(({ clock }) => { if (light.current) light.current.intensity = 1.2 + Math.sin(clock.getElapsedTime() * 12) * .7; }); return <group position={[2.05, 0, 0]}><mesh><sphereGeometry args={[.16, 20, 20]} /><meshBasicMaterial color="#ff64c1" /></mesh><pointLight ref={light} color="#ff4faf" intensity={2} distance={3.5} /></group> }

function GroundStation() { return <group position={[6.1, -3.7, 0]}><mesh><cylinderGeometry args={[1.55, 1.8, .35, 32]} /><meshStandardMaterial color="#48617b" metalness={.7} /></mesh><mesh position={[0, .7, 0]} rotation={[0, 0, -.55]}><cylinderGeometry args={[.72, .2, 1.4, 30, 1, true]} /><meshStandardMaterial color="#c1d0dd" metalness={.75} /></mesh><pointLight position={[.1, 1.25, 0]} color="#ff4eb7" intensity={2} distance={4} /></group> }

function OpticalLink({ ground, disturbed, acquiring }: { ground: boolean; disturbed: boolean; acquiring: boolean }) {
  const beam = useRef<THREE.Mesh>(null); useFrame(({ clock }) => { if (!beam.current) return; const t = clock.getElapsedTime(); const a = new THREE.Vector3(-5.3 + Math.sin(t * .42) * .8, Math.sin(t * .42) * 1.8, Math.cos(t * .42) * 1.15); const b = ground ? new THREE.Vector3(6.1, -2.45, 0) : new THREE.Vector3(5.3 + Math.sin(t * .42 + 2) * .8, Math.sin(t * .42 + 2) * 1.8, Math.cos(t * .42 + 2) * 1.15); if (disturbed) b.y += Math.sin(t * 13) * .3; const middle=a.clone().add(b).multiplyScalar(.5); beam.current.position.copy(middle); beam.current.scale.set(1, a.distanceTo(b), 1); beam.current.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),b.clone().sub(a).normalize()); }); return <mesh ref={beam}><cylinderGeometry args={[acquiring ? .035 : .055, acquiring ? .035 : .055, 1, 10]} /><meshBasicMaterial color="#ff4fb4" transparent opacity={acquiring ? .55 : .85} blending={THREE.AdditiveBlending} /></mesh>;
}
