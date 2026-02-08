import { useState, useRef, useCallback, MouseEvent } from 'react';

interface TiltStyle {
  transform: string;
  transition: string;
}

interface Use3DTiltOptions {
  maxTilt?: number;
  perspective?: number;
  scale?: number;
  speed?: number;
  glare?: boolean;
  maxGlare?: number;
}

interface Use3DTiltReturn {
  tiltStyle: TiltStyle;
  glareStyle: {
    opacity: number;
    transform: string;
  };
  onMouseMove: (e: MouseEvent<HTMLDivElement>) => void;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  ref: React.RefObject<HTMLDivElement>;
}

export const use3DTilt = (options: Use3DTiltOptions = {}): Use3DTiltReturn => {
  const {
    maxTilt = 10,
    perspective = 1000,
    scale = 1.02,
    speed = 400,
    glare = true,
    maxGlare = 0.3,
  } = options;

  const ref = useRef<HTMLDivElement>(null);
  const [isHovering, setIsHovering] = useState(false);
  const [tiltValues, setTiltValues] = useState({ x: 0, y: 0 });
  const [glarePosition, setGlarePosition] = useState({ x: 50, y: 50 });

  const calculateTilt = useCallback(
    (e: MouseEvent<HTMLDivElement>) => {
      if (!ref.current) return;

      const rect = ref.current.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;

      const mouseX = e.clientX - centerX;
      const mouseY = e.clientY - centerY;

      const tiltX = (mouseY / (rect.height / 2)) * -maxTilt;
      const tiltY = (mouseX / (rect.width / 2)) * maxTilt;

      setTiltValues({ x: tiltX, y: tiltY });

      if (glare) {
        const glareX = ((e.clientX - rect.left) / rect.width) * 100;
        const glareY = ((e.clientY - rect.top) / rect.height) * 100;
        setGlarePosition({ x: glareX, y: glareY });
      }
    },
    [maxTilt, glare]
  );

  const onMouseMove = useCallback(
    (e: MouseEvent<HTMLDivElement>) => {
      if (!isHovering) return;
      calculateTilt(e);
    },
    [calculateTilt, isHovering]
  );

  const onMouseEnter = useCallback(() => {
    setIsHovering(true);
  }, []);

  const onMouseLeave = useCallback(() => {
    setIsHovering(false);
    setTiltValues({ x: 0, y: 0 });
    setGlarePosition({ x: 50, y: 50 });
  }, []);

  const tiltStyle: TiltStyle = {
    transform: isHovering
      ? `perspective(${perspective}px) rotateX(${tiltValues.x}deg) rotateY(${tiltValues.y}deg) scale(${scale})`
      : `perspective(${perspective}px) rotateX(0deg) rotateY(0deg) scale(1)`,
    transition: `transform ${speed}ms cubic-bezier(0.03, 0.98, 0.52, 0.99)`,
  };

  const glareStyle = {
    opacity: isHovering ? maxGlare : 0,
    transform: `translate(${glarePosition.x - 50}%, ${glarePosition.y - 50}%)`,
  };

  return {
    tiltStyle,
    glareStyle,
    onMouseMove,
    onMouseEnter,
    onMouseLeave,
    ref,
  };
};
