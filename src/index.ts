import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';
import { ICommandPalette } from '@jupyterlab/apputils';
import {
  INotebookTracker,
  NotebookActions,
  NotebookPanel
} from '@jupyterlab/notebook';
import { ISettingRegistry } from '@jupyterlab/settingregistry';
import { Widget } from '@lumino/widgets';

import { NotebookRecorder, TrailEvent } from './recorder';
import { requestAPI } from './request';

const TOGGLE = 'nbtrail:toggle-recording';

/** Toolbar badge: recording must always be visible to the student (SPEC.md §2). */
class RecordingBadge extends Widget {
  constructor(private onClick: () => void) {
    super({ node: document.createElement('button') });
    this.addClass('nbtrail-badge');
    this.node.title = 'nbtrail: click to pause / resume recording';
    this.node.addEventListener('click', () => this.onClick());
  }

  setPaused(paused: boolean): void {
    this.node.textContent = paused ? '❚❚ nbtrail paused' : '● nbtrail';
    this.toggleClass('nbtrail-paused', paused);
  }
}

const plugin: JupyterFrontEndPlugin<void> = {
  id: 'nbtrail:plugin',
  description:
    'Proof of process for Jupyter: a tamper-evident, replayable record of how a notebook was built.',
  autoStart: true,
  requires: [INotebookTracker],
  optional: [ISettingRegistry, ICommandPalette],
  activate: async (
    app: JupyterFrontEnd,
    tracker: INotebookTracker,
    settingRegistry: ISettingRegistry | null,
    palette: ICommandPalette | null
  ) => {
    let enabled = true;
    let flushMs = 2000;
    if (settingRegistry) {
      try {
        const settings = await settingRegistry.load(plugin.id);
        enabled = settings.get('enabled').composite as boolean;
        flushMs = settings.get('flushIntervalMs').composite as number;
      } catch (reason) {
        console.error('nbtrail: failed to load settings', reason);
      }
    }
    if (!enabled) {
      console.log('nbtrail is disabled in settings');
      return;
    }

    const send = async (notebook: string, events: TrailEvent[]) => {
      await requestAPI('events', app.serviceManager.serverSettings, {
        method: 'POST',
        body: JSON.stringify({ notebook, events })
      });
    };

    const recorders = new Map<
      NotebookPanel,
      { rec: NotebookRecorder; badge: RecordingBadge }
    >();
    let paused = false;

    const setPaused = (value: boolean) => {
      paused = value;
      for (const { rec, badge } of recorders.values()) {
        rec.setPaused(value);
        badge.setPaused(value);
      }
      app.commands.notifyCommandChanged(TOGGLE);
    };

    tracker.widgetAdded.connect((_, panel) => {
      const rec = new NotebookRecorder(panel, send);
      const badge = new RecordingBadge(() => setPaused(!paused));
      badge.setPaused(paused);
      panel.toolbar.insertItem(10, 'nbtrail', badge);
      recorders.set(panel, { rec, badge });
      rec.setPaused(paused);
      void rec.start();
      panel.disposed.connect(() => recorders.delete(panel));
    });

    NotebookActions.executed.connect((_, args) => {
      for (const { rec } of recorders.values()) {
        rec.onExecuted(args);
      }
    });

    window.setInterval(() => {
      for (const { rec } of recorders.values()) {
        void rec.flush();
      }
    }, flushMs);

    app.commands.addCommand(TOGGLE, {
      label: () =>
        paused ? 'nbtrail: Resume recording' : 'nbtrail: Pause recording',
      execute: () => setPaused(!paused)
    });
    palette?.addItem({ command: TOGGLE, category: 'nbtrail' });

    console.log('nbtrail is recording');
  }
};

export default plugin;
