import { Button } from "@douyinfe/semi-ui";
import { Maximize2, Minimize2, Minus, FolderOpen, X } from "lucide-react";
import {
  CSSProperties,
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  lazy,
  MutableRefObject,
  useMemo,
  PointerEvent as ReactPointerEvent,
  useRef,
  useState,
  Suspense,
} from "react";
import { SANDBOX_CONTAINER_STATUS } from "../../shared/api/generated/constants";
import type { SandboxContainer } from "../../shared/api/types";
import { cx } from "../../shared/lib/className";
import {
  animateWindowFlight,
  buildFlight,
  buildWindowFlightStyle,
  cancelFlightFrame,
  clampWindowToViewport,
  type DockState,
  type DragState,
  type FlightState,
  getDraggedWindowPosition,
  getInitialFileManagerRect,
  getMaximizedRect,
  getResizedWindowSize,
  getWindowRect,
  type Rect,
  type ResizeState,
  type WindowStateBase,
} from "./floatingWindow";

const ContainerFileManager = lazy(() => import("./ContainerFileManager").then((module) => ({ default: module.ContainerFileManager })));

type FileManagerWindowState = WindowStateBase & {
  containerId: number;
  containerName: string;
  isMaximized: boolean;
  restoreRect: Rect | null;
};

type ContainerShellContextValue = {
  openFileManager: (container: SandboxContainer) => void;
  syncContainerWindows: (container: SandboxContainer | null) => void;
};

type FloatingWindowProps = {
  actions: ReactNode;
  children: ReactNode;
  className?: string;
  dockState: DockState;
  icon: ReactNode;
  isMaximized?: boolean;
  meta: string;
  onHeaderPointerDown: (event: ReactPointerEvent<HTMLDivElement>) => void;
  rect: Rect;
  resizeHandle?: ReactNode;
  title: string;
};

type FloatingWindowFlightProps = {
  flight: FlightState;
  frameRef: MutableRefObject<HTMLDivElement | null>;
  icon: ReactNode;
  style?: CSSProperties;
};

type MinimizedWindowButtonProps = {
  ariaLabel: string;
  className?: string;
  icon: ReactNode;
  onClick: () => void;
};

type FloatingWindowLayerProps = {
  actions: ReactNode;
  children: ReactNode;
  flight: FlightState | null;
  flightIcon: ReactNode;
  flightRef: MutableRefObject<HTMLDivElement | null>;
  flightStyle?: CSSProperties;
  icon: ReactNode;
  meta: string;
  minimizedAriaLabel: string;
  minimizedClassName?: string;
  minimizedIcon: ReactNode;
  onHeaderPointerDown: (event: ReactPointerEvent<HTMLDivElement>) => void;
  onRestore: () => void;
  resizeHandle?: ReactNode;
  state: WindowStateBase & { isMaximized?: boolean };
};

type WindowControlsProps = {
  closeAriaLabel: string;
  maximizeAriaLabel?: string;
  minimizeAriaLabel: string;
  isMaximized?: boolean;
  onClose: () => void;
  onMaximize?: () => void;
  onMinimize: () => void;
  restoreAriaLabel?: string;
};

const ContainerShellContext = createContext<ContainerShellContextValue | null>(null);

export function useContainerShell() {
  const value = useContext(ContainerShellContext);
  if (!value) throw new Error("useContainerShell must be used inside ContainerShellProvider");
  return value;
}

export function ContainerShellProvider({ children }: { children: ReactNode }) {
  const [fileManager, setFileManager] = useState<FileManagerWindowState | null>(null);
  const [fileManagerFlight, setFileManagerFlight] = useState<FlightState | null>(null);
  const fileManagerFlightRef = useRef<HTMLDivElement | null>(null);
  const fileManagerFlightFrameRef = useRef<number | null>(null);
  const fileManagerDragRef = useRef<DragState | null>(null);
  const resizeRef = useRef<ResizeState | null>(null);

  const closeFileManager = useCallback(() => {
    cancelFlightFrame(fileManagerFlightFrameRef);
    fileManagerDragRef.current = null;
    setFileManagerFlight(null);
    setFileManager(null);
  }, []);

  const minimizeFileManager = useCallback(() => {
    if (!fileManager) return;
    cancelFlightFrame(fileManagerFlightFrameRef);
    setFileManagerFlight(buildFlight(fileManager, "minimize", "files"));
    setFileManager((current) => current ? { ...current, dockState: "minimized" } : current);
  }, [fileManager]);

  const restoreFileManager = useCallback(() => {
    if (!fileManager) return;
    cancelFlightFrame(fileManagerFlightFrameRef);
    setFileManagerFlight(buildFlight(fileManager, "restore", "files"));
  }, [fileManager]);

  const toggleMaximizeFileManager = useCallback(() => {
    cancelFlightFrame(fileManagerFlightFrameRef);
    fileManagerDragRef.current = null;
    resizeRef.current = null;
    setFileManagerFlight(null);
    setFileManager((current) => {
      if (!current) return current;
      if (current.isMaximized) {
        const restoreRect = current.restoreRect ?? getWindowRect(current);
        return { ...current, ...restoreRect, isMaximized: false, restoreRect: null };
      }

      return {
        ...current,
        ...getMaximizedRect(),
        isMaximized: true,
        restoreRect: getWindowRect(current),
      };
    });
  }, []);

  const openFileManager = useCallback((container: SandboxContainer) => {
    if (container.status !== SANDBOX_CONTAINER_STATUS.RUNNING || container.control_proxy_host_port <= 0) return;

    cancelFlightFrame(fileManagerFlightFrameRef);
    setFileManagerFlight(null);
    setFileManager((current) => {
      if (current?.containerId === container.id) {
        return { ...current, title: container.container_name, containerName: container.container_name, dockState: "normal" };
      }

      return {
        containerId: container.id,
        title: container.container_name,
        containerName: container.container_name,
        dockState: "normal",
        isMaximized: false,
        restoreRect: null,
        ...getInitialFileManagerRect(),
      };
    });
  }, []);

  // 沙箱随会话切换/停止时，把文件管理器窗口跟随同步（关闭或重开）。
  const syncContainerWindows = useCallback((container: SandboxContainer | null) => {
    if (!fileManager) return;
    if (container && container.status === SANDBOX_CONTAINER_STATUS.RUNNING && container.control_proxy_host_port > 0) {
      openFileManager(container);
    } else {
      closeFileManager();
    }
  }, [closeFileManager, fileManager, openFileManager]);

  useEffect(() => () => closeFileManager(), [closeFileManager]);

  useEffect(() => () => {
    cancelFlightFrame(fileManagerFlightFrameRef);
  }, []);

  useEffect(() => {
    if (!fileManagerFlight || !fileManagerFlightRef.current) return;
    return animateWindowFlight(fileManagerFlightRef.current, fileManagerFlight, fileManagerFlightFrameRef, () => {
      if (fileManagerFlight.direction === "restore") {
        setFileManager((current) => current ? { ...current, dockState: "normal" } : current);
      }
      setFileManagerFlight(null);
    });
  }, [fileManagerFlight]);

  useEffect(() => {
    const onWindowResize = () => {
      setFileManager((current) => {
        if (!current) return current;
        if (current.isMaximized) return { ...current, ...getMaximizedRect() };
        return clampWindowToViewport(current);
      });
    };
    window.addEventListener("resize", onWindowResize);
    return () => window.removeEventListener("resize", onWindowResize);
  }, []);

  const onPointerMove = useCallback((event: PointerEvent) => {
    const fmDrag = fileManagerDragRef.current;
    if (fmDrag) {
      setFileManager((current) => current ? {
        ...current,
        ...getDraggedWindowPosition(fmDrag, event),
      } : current);
      return;
    }

    const resize = resizeRef.current;
    if (resize) {
      const nextSize = getResizedWindowSize(resize, event);
      setFileManager((current) => current ? { ...current, ...nextSize } : current);
    }
  }, []);

  const stopPointerAction = useCallback(() => {
    fileManagerDragRef.current = null;
    resizeRef.current = null;
  }, []);

  useEffect(() => {
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", stopPointerAction);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", stopPointerAction);
    };
  }, [onPointerMove, stopPointerAction]);

  const contextValue = useMemo<ContainerShellContextValue>(
    () => ({ openFileManager, syncContainerWindows }),
    [openFileManager, syncContainerWindows],
  );
  const fileManagerFlightStyle = fileManagerFlight ? buildWindowFlightStyle(fileManagerFlight) : undefined;

  return (
    <ContainerShellContext.Provider value={contextValue}>
      {children}
      {fileManager ? (
        <FloatingWindowLayer
          actions={(
            <WindowControls
              closeAriaLabel="关闭文件管理器"
              isMaximized={fileManager.isMaximized}
              maximizeAriaLabel="最大化文件管理器"
              minimizeAriaLabel="最小化文件管理器"
              onClose={closeFileManager}
              onMaximize={toggleMaximizeFileManager}
              onMinimize={minimizeFileManager}
              restoreAriaLabel="恢复文件管理器大小"
            />
          )}
          flight={fileManagerFlight}
          flightIcon={<FolderOpen size={15} />}
          flightRef={fileManagerFlightRef}
          flightStyle={fileManagerFlightStyle}
          icon={<FolderOpen size={16} />}
          meta="文件"
          minimizedAriaLabel="恢复文件管理器"
          minimizedClassName="filemanager-minimized-button"
          minimizedIcon={<FolderOpen size={20} />}
          onHeaderPointerDown={(event) => {
            if (fileManager.isMaximized) return;
            fileManagerDragRef.current = beginWindowDrag(fileManager, event, { capturePointer: true });
          }}
          onRestore={restoreFileManager}
          resizeHandle={(
            <div
              className="shell-resize-handle"
              onPointerDown={(event) => {
                if (fileManager.isMaximized) return;
                resizeRef.current = beginWindowResize("filemanager", fileManager, event);
              }}
            />
          )}
          state={fileManager}
        >
          <Suspense fallback={<div className="file-manager-loading">文件加载中…</div>}>
            <ContainerFileManager containerId={fileManager.containerId} />
          </Suspense>
        </FloatingWindowLayer>
      ) : null}
    </ContainerShellContext.Provider>
  );
}

function FloatingWindowLayer({
  actions,
  children,
  flight,
  flightIcon,
  flightRef,
  flightStyle,
  icon,
  meta,
  minimizedAriaLabel,
  minimizedClassName,
  minimizedIcon,
  onHeaderPointerDown,
  onRestore,
  resizeHandle,
  state,
}: FloatingWindowLayerProps) {
  return (
    <>
      <FloatingWindow
        actions={actions}
        dockState={state.dockState}
        icon={icon}
        isMaximized={state.isMaximized}
        meta={meta}
        rect={state}
        title={state.title}
        onHeaderPointerDown={onHeaderPointerDown}
        resizeHandle={resizeHandle}
      >
        {children}
      </FloatingWindow>
      {state.dockState === "minimized" && !flight ? (
        <MinimizedWindowButton className={minimizedClassName} ariaLabel={minimizedAriaLabel} icon={minimizedIcon} onClick={onRestore} />
      ) : null}
      {flight ? (
        <FloatingWindowFlight frameRef={flightRef} flight={flight} icon={flightIcon} style={flightStyle} />
      ) : null}
    </>
  );
}

function WindowControls({
  closeAriaLabel,
  isMaximized = false,
  maximizeAriaLabel,
  minimizeAriaLabel,
  onClose,
  onMaximize,
  onMinimize,
  restoreAriaLabel,
}: WindowControlsProps) {
  return (
    <>
      <Button icon={<Minus size={14} />} theme="borderless" type="tertiary" onClick={onMinimize} aria-label={minimizeAriaLabel} />
      {onMaximize ? (
        <Button icon={isMaximized ? <Minimize2 size={14} /> : <Maximize2 size={14} />} theme="borderless" type="tertiary" onClick={onMaximize} aria-label={isMaximized ? restoreAriaLabel : maximizeAriaLabel} />
      ) : null}
      <Button icon={<X size={14} />} theme="borderless" type="tertiary" onClick={onClose} aria-label={closeAriaLabel} />
    </>
  );
}

function FloatingWindow({
  actions,
  children,
  className,
  dockState,
  icon,
  isMaximized = false,
  meta,
  onHeaderPointerDown,
  rect,
  resizeHandle,
  title,
}: FloatingWindowProps) {
  return (
    <div className={buildWindowClassName(className, dockState, isMaximized)} style={buildWindowStyle(rect)}>
      <FloatingWindowHeader
        actions={actions}
        icon={icon}
        meta={meta}
        title={title}
        onPointerDown={onHeaderPointerDown}
      />
      {children}
      {resizeHandle}
    </div>
  );
}

function FloatingWindowHeader({
  actions,
  icon,
  meta,
  onPointerDown,
  title,
}: Pick<FloatingWindowProps, "actions" | "icon" | "meta" | "title"> & {
  onPointerDown: (event: ReactPointerEvent<HTMLDivElement>) => void;
}) {
  return (
    <div className="shell-window-header" onPointerDown={onPointerDown}>
      <div className="shell-window-title">
        {icon}
        <span>{title}</span>
        <em>{meta}</em>
      </div>
      <div className="shell-window-actions" onPointerDown={(event) => event.stopPropagation()}>
        {actions}
      </div>
    </div>
  );
}

function FloatingWindowFlight({ flight, frameRef, icon, style }: FloatingWindowFlightProps) {
  return (
    <div ref={frameRef} className={cx("shell-flight", `shell-flight-${flight.direction}`)} style={style}>
      <div className="shell-flight-header">
        {icon}
        <span>{flight.title}</span>
        <em>{flight.meta}</em>
      </div>
      <div className="shell-flight-body" />
    </div>
  );
}

function MinimizedWindowButton({ ariaLabel, className, icon, onClick }: MinimizedWindowButtonProps) {
  return (
    <button className={cx("shell-minimized-button", className)} type="button" onClick={onClick} aria-label={ariaLabel}>
      {icon}
    </button>
  );
}

function buildWindowClassName(className: string | undefined, dockState: DockState, isMaximized: boolean) {
  return cx(
    "shell-window",
    className,
    dockState === "minimized" && "shell-window-hidden",
    isMaximized && "shell-window-maximized",
  );
}

function beginWindowDrag(
  rect: Rect,
  event: ReactPointerEvent<HTMLDivElement>,
  options: { capturePointer?: boolean } = {},
): DragState {
  if (options.capturePointer) event.currentTarget.setPointerCapture(event.pointerId);
  return { x: rect.x, y: rect.y, startX: event.clientX, startY: event.clientY };
}

function beginWindowResize(
  target: ResizeState["target"],
  rect: Rect,
  event: ReactPointerEvent<HTMLDivElement>,
): ResizeState {
  event.currentTarget.setPointerCapture(event.pointerId);
  return { target, width: rect.width, height: rect.height, startX: event.clientX, startY: event.clientY };
}

function buildWindowStyle(rect: Rect) {
  return {
    left: rect.x,
    top: rect.y,
    width: rect.width,
    height: rect.height,
  } satisfies CSSProperties;
}
