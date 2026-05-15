"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import { HubConnectionBuilder, HubConnection, LogLevel } from "@microsoft/signalr";
import { LatestReading } from "@/lib/types";
import { negotiateSignalR } from "@/lib/api";

interface ConnectionStatusEvent {
  patientId: string;
  deviceOnline: boolean;
  secondsSinceReading: number | null;
}

interface AlertTriggeredEvent {
  patientId: string;
  id: string;
  alertType: string;
  severity: string;
  message: string;
}

interface AlertResolvedEvent {
  patientId: string;
  id: string;
  alertType: string;
  resolvedAt: string;
}

interface UseSignalROptions {
  patientId: string;
  onNewReading: (reading: LatestReading) => void;
  onConnectionStatus?: (status: ConnectionStatusEvent) => void;
  onAlertTriggered?: (alert: AlertTriggeredEvent) => void;
  onAlertResolved?: (alert: AlertResolvedEvent) => void;
}

export function useSignalR({ patientId, onNewReading, onConnectionStatus, onAlertTriggered, onAlertResolved }: UseSignalROptions) {
  const connectionRef = useRef<HubConnection | null>(null);
  const [connected, setConnected] = useState(false);

  const onNewReadingRef = useRef(onNewReading);
  onNewReadingRef.current = onNewReading;
  const onConnectionStatusRef = useRef(onConnectionStatus);
  onConnectionStatusRef.current = onConnectionStatus;
  const onAlertTriggeredRef = useRef(onAlertTriggered);
  onAlertTriggeredRef.current = onAlertTriggered;
  const onAlertResolvedRef = useRef(onAlertResolved);
  onAlertResolvedRef.current = onAlertResolved;

  const connect = useCallback(async () => {
    if (connectionRef.current) return;

    try {
      const { url, accessToken } = await negotiateSignalR();

      const connection = new HubConnectionBuilder()
        .withUrl(url, { accessTokenFactory: () => accessToken })
        .withAutomaticReconnect()
        .configureLogging(LogLevel.Warning)
        .build();

      connection.on("newReading", (data: LatestReading) => {
        if (data.patientId === patientId) {
          onNewReadingRef.current(data);
        }
      });

      connection.on("connectionStatus", (data: ConnectionStatusEvent) => {
        if (data.patientId === patientId && onConnectionStatusRef.current) {
          onConnectionStatusRef.current(data);
        }
      });

      connection.on("alertTriggered", (data: AlertTriggeredEvent) => {
        if (data.patientId === patientId && onAlertTriggeredRef.current) {
          onAlertTriggeredRef.current(data);
        }
      });

      connection.on("alertResolved", (data: AlertResolvedEvent) => {
        if (data.patientId === patientId && onAlertResolvedRef.current) {
          onAlertResolvedRef.current(data);
        }
      });

      connection.onclose(() => setConnected(false));
      connection.onreconnected(() => setConnected(true));
      connection.onreconnecting(() => setConnected(false));

      await connection.start();
      connectionRef.current = connection;
      setConnected(true);
    } catch (err) {
      console.error("SignalR connection failed:", err);
      setConnected(false);
    }
  }, [patientId]);

  useEffect(() => {
    connect();
    return () => {
      const conn = connectionRef.current;
      if (conn) {
        connectionRef.current = null;
        conn.stop();
      }
    };
  }, [connect]);

  return { connected };
}
