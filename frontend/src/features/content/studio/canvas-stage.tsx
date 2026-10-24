"use client";

/**
 * The interactive design canvas. Client-only (loaded with next/dynamic, ssr: false)
 * because Konva needs the browser canvas.
 */

import type Konva from "konva";
import { useEffect, useRef, useState } from "react";
import {
  Ellipse,
  Group,
  Image as KImage,
  Layer,
  Rect,
  Stage,
  Text,
  Transformer,
} from "react-konva";

import { assetUrl, type DesignElement, type ImageElement, type Page } from "./document";
import {
  ellipseAttrs,
  imageLayout,
  loadImage,
  rectAttrs,
  roundedClip,
  textAttrs,
} from "./konva-attrs";

export interface CanvasStageProps {
  orgId: string;
  width: number;
  height: number;
  page: Page;
  scale: number;
  selectedId: string | null;
  readOnly: boolean;
  onSelect: (id: string | null) => void;
  onChange: (id: string, patch: Partial<DesignElement>) => void;
  onEditText: (id: string) => void;
}

function useImage(url: string) {
  const [img, setImg] = useState<HTMLImageElement | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    void loadImage(url).then((loaded) => live && setImg(loaded));
    return () => {
      live = false;
    };
  }, [url]);
  return img;
}

function ImageNode({
  el,
  orgId,
  common,
}: {
  el: ImageElement;
  orgId: string;
  common: Record<string, unknown>;
}) {
  const img = useImage(assetUrl(orgId, el.asset));
  const natural = img ? { width: img.naturalWidth, height: img.naturalHeight } : null;
  const { inner, crop } = imageLayout(el, natural);
  return (
    <Group
      {...common}
      x={el.x}
      y={el.y}
      width={el.width}
      height={el.height}
      rotation={el.rotation ?? 0}
      opacity={el.opacity ?? 1}
      clipFunc={(ctx) => roundedClip(ctx, el.width, el.height, el.corner_radius)}
    >
      {/* Hit area so empty (contain) regions are still selectable. */}
      <Rect width={el.width} height={el.height} fill={img ? "rgba(0,0,0,0)" : "#e4e4e7"} />
      {img ? (
        <KImage image={img} {...inner} crop={crop} />
      ) : (
        <Text
          text={img === null ? "Image unavailable" : "Loading…"}
          width={el.width}
          height={el.height}
          align="center"
          verticalAlign="middle"
          fontSize={Math.max(14, el.width / 14)}
          fill="#71717a"
        />
      )}
    </Group>
  );
}

export default function CanvasStage({
  orgId,
  width,
  height,
  page,
  scale,
  selectedId,
  readOnly,
  onSelect,
  onChange,
  onEditText,
}: CanvasStageProps) {
  const transformer = useRef<Konva.Transformer>(null);
  const stage = useRef<Konva.Stage>(null);
  const selected = page.elements.find((e) => e.id === selectedId);

  useEffect(() => {
    const tr = transformer.current;
    if (!tr) return;
    const node = selectedId && !selected?.locked ? stage.current?.findOne(`#${selectedId}`) : null;
    tr.nodes(node ? [node] : []);
    tr.getLayer()?.batchDraw();
  }, [selectedId, selected?.locked, page]);

  const r = (n: number) => Math.round(n * 100) / 100;
  const commonFor = (el: DesignElement) => ({
    id: el.id,
    name: "element",
    draggable: !readOnly && !el.locked,
    onMouseDown: () => onSelect(el.id),
    onTap: () => onSelect(el.id),
    onDblClick: () => el.type === "text" && onEditText(el.id),
    onDblTap: () => el.type === "text" && onEditText(el.id),
    onDragEnd: (e: Konva.KonvaEventObject<DragEvent>) => {
      const node = e.target;
      if (el.type === "ellipse") {
        onChange(el.id, { x: r(node.x() - el.width / 2), y: r(node.y() - el.height / 2) });
      } else {
        onChange(el.id, { x: r(node.x()), y: r(node.y()) });
      }
    },
    onTransformEnd: (e: Konva.KonvaEventObject<Event>) => {
      const node = e.target;
      const w = r(Math.max(5, el.width * node.scaleX()));
      const h = r(Math.max(5, el.height * node.scaleY()));
      node.scaleX(1);
      node.scaleY(1);
      const rotation = Math.round(node.rotation() * 10) / 10;
      if (el.type === "ellipse") {
        onChange(el.id, {
          x: r(node.x() - w / 2),
          y: r(node.y() - h / 2),
          width: w,
          height: h,
          rotation,
        });
      } else {
        onChange(el.id, { x: r(node.x()), y: r(node.y()), width: w, height: h, rotation });
      }
    },
  });

  return (
    <Stage
      ref={stage}
      width={Math.round(width * scale)}
      height={Math.round(height * scale)}
      scaleX={scale}
      scaleY={scale}
      onMouseDown={(e) => {
        if (e.target === e.target.getStage() || e.target.name() === "background") onSelect(null);
      }}
      onTouchStart={(e) => {
        if (e.target === e.target.getStage() || e.target.name() === "background") onSelect(null);
      }}
    >
      <Layer>
        <Rect
          name="background"
          x={0}
          y={0}
          width={width}
          height={height}
          fill={page.background === "transparent" ? "#ffffff" : page.background}
        />
        {page.elements.map((el) => {
          const common = commonFor(el);
          if (el.type === "text") return <Text key={el.id} {...common} {...textAttrs(el)} />;
          if (el.type === "rect") return <Rect key={el.id} {...common} {...rectAttrs(el)} />;
          if (el.type === "ellipse")
            return <Ellipse key={el.id} {...common} {...ellipseAttrs(el)} />;
          if (el.type === "image")
            return <ImageNode key={el.id} el={el} orgId={orgId} common={common} />;
          return null;
        })}
        {!readOnly && (
          <Transformer
            ref={transformer}
            rotateEnabled
            keepRatio={selected?.type === "image"}
            ignoreStroke
            borderStroke="#4338ca"
            anchorStroke="#4338ca"
            anchorSize={10}
            boundBoxFunc={(oldBox, newBox) =>
              newBox.width < 5 || newBox.height < 5 ? oldBox : newBox
            }
          />
        )}
      </Layer>
    </Stage>
  );
}
