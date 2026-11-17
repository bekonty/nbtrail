import { NotebookActions, NotebookPanel } from '@jupyterlab/notebook';
import { ICellModel } from '@jupyterlab/cells';

/** A client-side event (SPEC.md §4). The server adds v, seq, srv_ts, prev, hash. */
export type TrailEvent =
  | {
      kind: 'session';
      ts: number;
      action: 'start' | 'pause' | 'resume' | 'stop';
    }
  | {
      kind: 'snapshot';
      ts: number;
      cells: { id: string; type: string; source: string }[];
    }
  | { kind: 'edit'; ts: number; cell: string; delta: DeltaOp[] }
  | { kind: 'run'; ts: number; cell: string; ok: boolean; error: string | null }
  | { kind: 'paste'; ts: number; cell: string; chars: number };

export type DeltaOp = { insert?: string; delete?: number; retain?: number };

export type Sender = (notebook: string, events: TrailEvent[]) => Promise<void>;

/**
 * Records one open notebook. Events are queued and sent in order by flush();
 * if a send fails they stay at the front of the queue and are retried.
 */
export class NotebookRecorder {
  private queue: TrailEvent[] = [];
  private sending = false;
  private watched = new WeakSet<ICellModel>();
  private _paused = false;
  private _disposed = false;

  constructor(
    readonly panel: NotebookPanel,
    private send: Sender
  ) {}

  get paused(): boolean {
    return this._paused;
  }

  async start(): Promise<void> {
    await this.panel.context.ready;
    const model = this.panel.content.model;
    if (!model || this._disposed) {
      return;
    }
    this.push({ kind: 'session', ts: Date.now(), action: 'start' });
    this.snapshot();
    for (const cell of model.cells) {
      this.watch(cell);
    }
    // Structure changed (add / delete / move): watch new cells, write a keyframe.
    model.cells.changed.connect((_, change) => {
      for (const cell of change.newValues) {
        this.watch(cell);
      }
      this.snapshot();
    }, this);

    this.panel.content.node.addEventListener('paste', this.onPaste, true);
    this.panel.disposed.connect(() => this.dispose());
  }

  setPaused(paused: boolean): void {
    if (paused === this._paused) {
      return;
    }
    // Write the session event while recording is still on, so it is never dropped.
    if (paused) {
      this.push({ kind: 'session', ts: Date.now(), action: 'pause' });
      this._paused = true;
    } else {
      this._paused = false;
      this.push({ kind: 'session', ts: Date.now(), action: 'resume' });
      this.snapshot(); // edits made while paused are not in the log
    }
  }

  /** Called by the global NotebookActions.executed listener. */
  onExecuted(args: {
    notebook: unknown;
    cell: { model: ICellModel };
    success: boolean;
    error?: { errorName?: string } | null;
  }): void {
    if (args.notebook !== this.panel.content) {
      return;
    }
    this.push({
      kind: 'run',
      ts: Date.now(),
      cell: args.cell.model.id,
      ok: args.success,
      error: args.success ? null : (args.error?.errorName ?? 'Error')
    });
  }

  async flush(): Promise<void> {
    if (this.sending || this.queue.length === 0) {
      return;
    }
    this.sending = true;
    const batch = this.queue.splice(0, 500);
    try {
      await this.send(this.panel.context.path, batch);
    } catch (reason) {
      this.queue.unshift(...batch);
      console.warn('nbtrail: send failed, will retry', reason);
    } finally {
      this.sending = false;
    }
  }

  dispose(): void {
    if (this._disposed) {
      return;
    }
    this.push({ kind: 'session', ts: Date.now(), action: 'stop' });
    void this.flush();
    this._disposed = true;
    this.panel.content.node.removeEventListener('paste', this.onPaste, true);
  }

  private push(event: TrailEvent): void {
    if (!this._paused && !this._disposed) {
      this.queue.push(event);
    }
  }

  private snapshot(): void {
    const model = this.panel.content.model;
    if (!model) {
      return;
    }
    const cells = [];
    for (const cell of model.cells) {
      cells.push({
        id: cell.id,
        type: cell.type,
        source: cell.sharedModel.getSource()
      });
    }
    this.push({ kind: 'snapshot', ts: Date.now(), cells });
  }

  private watch(cell: ICellModel): void {
    if (this.watched.has(cell)) {
      return;
    }
    this.watched.add(cell);
    cell.sharedModel.changed.connect((_, change) => {
      if (change.sourceChange) {
        this.push({
          kind: 'edit',
          ts: Date.now(),
          cell: cell.id,
          delta: change.sourceChange as DeltaOp[]
        });
      }
    }, this);
  }

  // Only the size is logged here; the pasted text itself arrives via the edit delta.
  private onPaste = (e: ClipboardEvent): void => {
    const cell = this.panel.content.activeCell;
    const text = e.clipboardData?.getData('text') ?? '';
    if (cell && text.length > 0) {
      this.push({
        kind: 'paste',
        ts: Date.now(),
        cell: cell.model.id,
        chars: text.length
      });
    }
  };
}

export { NotebookActions };
