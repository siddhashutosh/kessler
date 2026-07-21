// 3D orbital scene (FR-UI-1): Earth, orbit rings from backend ECI tracks,
// conjunction marker at the sampled closest-approach geometry.
import { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Line, OrbitControls, Stars } from "@react-three/drei";
import * as THREE from "three";
import type { Track } from "../types";

const EARTH_RADIUS_KM = 6371;
const SCALE = 1 / EARTH_RADIUS_KM; // 1 scene unit = Earth radius

function toScene([x, y, z]: [number, number, number]): [number, number, number] {
  // TEME (z = north) -> three.js (y = up)
  return [x * SCALE, z * SCALE, -y * SCALE];
}

function Earth() {
  const group = useRef<THREE.Group>(null);
  useFrame((_, delta) => {
    if (group.current) group.current.rotation.y += delta * 0.008;
  });

  const graticule = useMemo(() => {
    const lines: [number, number, number][][] = [];
    for (let lat = -60; lat <= 60; lat += 30) {
      const ring: [number, number, number][] = [];
      const r = Math.cos((lat * Math.PI) / 180);
      const y = Math.sin((lat * Math.PI) / 180);
      for (let lon = 0; lon <= 360; lon += 6) {
        const a = (lon * Math.PI) / 180;
        ring.push([r * Math.cos(a), y, r * Math.sin(a)]);
      }
      lines.push(ring);
    }
    for (let lon = 0; lon < 180; lon += 30) {
      const a = (lon * Math.PI) / 180;
      const meridian: [number, number, number][] = [];
      for (let t = 0; t <= 360; t += 6) {
        const b = (t * Math.PI) / 180;
        meridian.push([
          Math.sin(b) * Math.cos(a),
          Math.cos(b),
          Math.sin(b) * Math.sin(a),
        ]);
      }
      lines.push(meridian);
    }
    return lines;
  }, []);

  return (
    <group ref={group}>
      <mesh>
        <sphereGeometry args={[1, 64, 64]} />
        <meshStandardMaterial color="#0d2038" roughness={0.85} metalness={0.1} />
      </mesh>
      {graticule.map((pts, i) => (
        <Line
          key={i}
          points={pts.map(([x, y, z]) => [x * 1.001, y * 1.001, z * 1.001])}
          color="#1d3a5f"
          lineWidth={0.6}
          transparent
          opacity={0.7}
        />
      ))}
      {/* atmosphere rim */}
      <mesh>
        <sphereGeometry args={[1.03, 48, 48]} />
        <meshBasicMaterial color="#59d8ff" transparent opacity={0.045} side={THREE.BackSide} />
      </mesh>
    </group>
  );
}

function OrbitPath({ track, color }: { track: Track; color: string }) {
  const points = useMemo(
    () => track.points.map((p) => toScene(p.r_eci_km)),
    [track],
  );
  if (points.length < 2) return null;
  return (
    <>
      <Line points={points} color={color} lineWidth={1.4} transparent opacity={0.85} />
      <mesh position={points[0]}>
        <sphereGeometry args={[0.014, 16, 16]} />
        <meshBasicMaterial color={color} />
      </mesh>
    </>
  );
}

function ConjunctionMarker({ position }: { position: [number, number, number] }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (ref.current) {
      const s = 1 + 0.35 * Math.sin(clock.elapsedTime * 4);
      ref.current.scale.setScalar(s);
    }
  });
  return (
    <group position={position}>
      <mesh ref={ref}>
        <sphereGeometry args={[0.02, 16, 16]} />
        <meshBasicMaterial color="#ff5d5d" transparent opacity={0.9} />
      </mesh>
      <mesh>
        <ringGeometry args={[0.035, 0.04, 32]} />
        <meshBasicMaterial color="#ff5d5d" transparent opacity={0.5} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

function closestApproachPoint(a: Track, b: Track): [number, number, number] | null {
  if (!a.points.length || !b.points.length) return null;
  let best = Infinity;
  let bestPos: [number, number, number] | null = null;
  const n = Math.min(a.points.length, b.points.length);
  for (let i = 0; i < n; i++) {
    const pa = a.points[i].r_eci_km;
    const pb = b.points[i].r_eci_km;
    const d =
      (pa[0] - pb[0]) ** 2 + (pa[1] - pb[1]) ** 2 + (pa[2] - pb[2]) ** 2;
    if (d < best) {
      best = d;
      bestPos = [
        (pa[0] + pb[0]) / 2,
        (pa[1] + pb[1]) / 2,
        (pa[2] + pb[2]) / 2,
      ];
    }
  }
  return bestPos ? toScene(bestPos) : null;
}

export default function Globe3D({
  primary,
  secondary,
}: {
  primary: Track | null;
  secondary: Track | null;
}) {
  const marker =
    primary && secondary ? closestApproachPoint(primary, secondary) : null;

  return (
    <Canvas
      camera={{ position: [0, 1.4, 3.4], fov: 45 }}
      gl={{ antialias: true, alpha: false }}
      style={{ background: "#05070d" }}
    >
      <ambientLight intensity={0.35} />
      <directionalLight position={[5, 3, 5]} intensity={1.4} color="#cfe4ff" />
      <Stars radius={60} depth={30} count={2200} factor={2.4} saturation={0} fade speed={0.4} />
      <Earth />
      {primary && <OrbitPath track={primary} color="#59d8ff" />}
      {secondary && <OrbitPath track={secondary} color="#ffb454" />}
      {marker && <ConjunctionMarker position={marker} />}
      <OrbitControls
        enablePan={false}
        minDistance={1.6}
        maxDistance={8}
        enableDamping
        dampingFactor={0.08}
      />
    </Canvas>
  );
}
