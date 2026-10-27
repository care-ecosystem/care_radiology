/** @type {AppTypes.Config} */

window.config = {
  routerBasename: '/',
  // Embedded in a care iframe, so the logo, patient banner and worklist link
  // are redundant — and on a phone they overlap the toolbar. Dropping them
  // gives the toolbar the full width of the header row.
  whiteLabeling: {
    createLogoComponentFn: React =>
      React.createElement('div', { style: { display: 'none' } }),
  },
  extensions: [],
  modes: [],
  /*
    The longitudinal mode opens with its left "Studies" panel expanded (280px),
    which swallows a 320px screen. Start both side panels collapsed instead, so
    each is a tap-to-open strip. `layoutTemplate` replaces the whole props
    object, so the panel/viewport ids below are restated verbatim from
    ohif-mode-longitudinal.js — re-resolve them if the image is upgraded.
  */
  modesConfiguration: {
    '@ohif/mode-longitudinal': {
      routes: [
        {
          path: 'longitudinal',
          layoutTemplate: () => ({
            id: '@ohif/extension-default.layoutTemplateModule.viewerLayout',
            props: {
              leftPanels: ['@ohif/extension-measurement-tracking.panelModule.seriesList'],
              leftPanelClosed: true,
              rightPanels: [
                '@ohif/extension-cornerstone.panelModule.panelSegmentation',
                '@ohif/extension-measurement-tracking.panelModule.trackedMeasurements',
              ],
              rightPanelClosed: true,
              viewports: [
                {
                  namespace:
                    '@ohif/extension-measurement-tracking.viewportModule.cornerstone-tracked',
                  displaySetsToDisplay: [
                    '@ohif/extension-default.sopClassHandlerModule.stack',
                    '@ohif/extension-dicom-video.sopClassHandlerModule.dicom-video',
                    '@ohif/extension-cornerstone-dicom-sr.sopClassHandlerModule.dicom-sr-3d',
                    '@ohif/extension-cornerstone.sopClassHandlerModule.DicomMicroscopySopClassHandler',
                  ],
                },
                {
                  namespace: '@ohif/extension-cornerstone-dicom-sr.viewportModule.dicom-sr',
                  displaySetsToDisplay: [
                    '@ohif/extension-cornerstone-dicom-sr.sopClassHandlerModule.dicom-sr',
                  ],
                },
                {
                  namespace: '@ohif/extension-dicom-pdf.viewportModule.dicom-pdf',
                  displaySetsToDisplay: [
                    '@ohif/extension-dicom-pdf.sopClassHandlerModule.dicom-pdf',
                  ],
                },
                {
                  namespace: '@ohif/extension-cornerstone-dicom-seg.viewportModule.dicom-seg',
                  displaySetsToDisplay: [
                    '@ohif/extension-cornerstone-dicom-seg.sopClassHandlerModule.dicom-seg',
                  ],
                },
                {
                  namespace: '@ohif/extension-cornerstone-dicom-pmap.viewportModule.dicom-pmap',
                  displaySetsToDisplay: [
                    '@ohif/extension-cornerstone-dicom-pmap.sopClassHandlerModule.dicom-pmap',
                  ],
                },
                {
                  namespace: '@ohif/extension-cornerstone-dicom-rt.viewportModule.dicom-rt',
                  displaySetsToDisplay: [
                    '@ohif/extension-cornerstone-dicom-rt.sopClassHandlerModule.dicom-rt',
                  ],
                },
              ],
            },
          }),
        },
      ],
    },
  },
  customizationService: {},
  showStudyList: false,
  investigationalUseDialog: { option: 'never' },
  // 'disabled' | 'visible' | 'visibleCollapsed' | 'visibleReadOnly'
  showPatientInfo: 'disabled',
  // some windows systems have issues with more than 3 web workers
  maxNumberOfWebWorkers: 3,
  // below flag is for performance reasons, but it might not work for all servers
  showWarningMessageForCrossOrigin: true,
  showCPUFallbackMessage: true,
  showLoadingIndicator: true,
  experimentalStudyBrowserSort: false,
  strictZSpacingForVolumeViewport: true,
  groupEnabledModesFirst: true,
  maxNumRequests: {
    interaction: 100,
    thumbnail: 75,
    prefetch: 25,
  },
  defaultDataSourceName: 'dicomweb',
  dataSources: [
    {
      namespace: '@ohif/extension-default.dataSourcesModule.dicomweb',
      sourceName: 'dicomweb',
      configuration: {
        friendlyName: 'DCM4CHE Server',
        name: 'dcm4che_server',
        wadoUriRoot: 'http://localhost:32314/dicomweb/dcm4chee-arc/aets/DCM4CHEE/wado',
        qidoRoot: 'http://localhost:32314/dicomweb/dcm4chee-arc/aets/DCM4CHEE/rs',
        wadoRoot: 'http://localhost:32314/dicomweb/dcm4chee-arc/aets/DCM4CHEE/rs',
        qidoSupportsIncludeField: false,
        imageRendering: 'wadors',
        thumbnailRendering: 'wadors',
        enableStudyLazyLoad: true,
        supportsFuzzyMatching: false,
        supportsWildcard: true,
        // staticWado: true,
        singlepart: 'bulkdata,video',
        // whether the data source should use retrieveBulkData to grab metadata,
        // and in case of relative path, what would it be relative to, options
        // are in the series level or study level (some servers like series some study)
        bulkDataURI: {
          enabled: true,
          relativeResolution: 'studies',
          transform: url => url.replace('/pixeldata.mp4', '/rendered'),
        },
        omitQuotationForMultipartRequest: true,
      },
    },
  ],
  httpErrorHandler: error => {
    // This is 429 when rejected from the public idc sandbox too often.
    console.warn(error.status);

    // Could use services manager here to bring up a dialog/modal if needed.
    console.warn('test, navigate to https://ohif.org/');
  },
  // whiteLabeling: {
  //   /* Optional: Should return a React component to be rendered in the "Logo" section of the application's Top Navigation bar */
  //   createLogoComponentFn: function (React) {
  //     return React.createElement(
  //       'a',
  //       {
  //         target: '_self',
  //         rel: 'noopener noreferrer',
  //         className: 'text-purple-600 line-through',
  //         href: '/',
  //       },
  //       React.createElement('img',
  //         {
  //           src: './assets/customLogo.svg',
  //           className: 'w-8 h-8',
  //         }
  //       ))
  //   },
  // },
  hotkeys: [
    {
      commandName: 'incrementActiveViewport',
      label: 'Next Viewport',
      keys: ['right'],
    },
    {
      commandName: 'decrementActiveViewport',
      label: 'Previous Viewport',
      keys: ['left'],
    },
    { commandName: 'rotateViewportCW', label: 'Rotate Right', keys: ['r'] },
    { commandName: 'rotateViewportCCW', label: 'Rotate Left', keys: ['l'] },
    { commandName: 'invertViewport', label: 'Invert', keys: ['i'] },
    {
      commandName: 'flipViewportHorizontal',
      label: 'Flip Horizontally',
      keys: ['h'],
    },
    {
      commandName: 'flipViewportVertical',
      label: 'Flip Vertically',
      keys: ['v'],
    },
    { commandName: 'scaleUpViewport', label: 'Zoom In', keys: ['+'] },
    { commandName: 'scaleDownViewport', label: 'Zoom Out', keys: ['-'] },
    { commandName: 'fitViewportToWindow', label: 'Zoom to Fit', keys: ['='] },
    { commandName: 'resetViewport', label: 'Reset', keys: ['space'] },
    { commandName: 'nextImage', label: 'Next Image', keys: ['down'] },
    { commandName: 'previousImage', label: 'Previous Image', keys: ['up'] },
    // {
    //   commandName: 'previousViewportDisplaySet',
    //   label: 'Previous Series',
    //   keys: ['pagedown'],
    // },
    // {
    //   commandName: 'nextViewportDisplaySet',
    //   label: 'Next Series',
    //   keys: ['pageup'],
    // },
    {
      commandName: 'setToolActive',
      commandOptions: { toolName: 'Zoom' },
      label: 'Zoom',
      keys: ['z'],
    },
    // ~ Window level presets
    {
      commandName: 'windowLevelPreset1',
      label: 'W/L Preset 1',
      keys: ['1'],
    },
    {
      commandName: 'windowLevelPreset2',
      label: 'W/L Preset 2',
      keys: ['2'],
    },
    {
      commandName: 'windowLevelPreset3',
      label: 'W/L Preset 3',
      keys: ['3'],
    },
    {
      commandName: 'windowLevelPreset4',
      label: 'W/L Preset 4',
      keys: ['4'],
    },
    {
      commandName: 'windowLevelPreset5',
      label: 'W/L Preset 5',
      keys: ['5'],
    },
    {
      commandName: 'windowLevelPreset6',
      label: 'W/L Preset 6',
      keys: ['6'],
    },
    {
      commandName: 'windowLevelPreset7',
      label: 'W/L Preset 7',
      keys: ['7'],
    },
    {
      commandName: 'windowLevelPreset8',
      label: 'W/L Preset 8',
      keys: ['8'],
    },
    {
      commandName: 'windowLevelPreset9',
      label: 'W/L Preset 9',
      keys: ['9'],
    },
  ],
  tours: [
    {
      id: 'basicViewerTour',
      route: '/viewer',
      steps: [
        {
          id: 'scroll',
          title: 'Scrolling Through Images',
          text: 'You can scroll through the images using the mouse wheel or scrollbar.',
          attachTo: {
            element: '.viewport-element',
            on: 'top',
          },
          advanceOn: {
            selector: '.cornerstone-viewport-element',
            event: 'CORNERSTONE_TOOLS_MOUSE_WHEEL',
          },
          beforeShowPromise: () => waitForElement('.viewport-element'),
        },
        {
          id: 'zoom',
          title: 'Zooming In and Out',
          text: 'You can zoom the images using the right click.',
          attachTo: {
            element: '.viewport-element',
            on: 'left',
          },
          advanceOn: {
            selector: '.cornerstone-viewport-element',
            event: 'CORNERSTONE_TOOLS_MOUSE_UP',
          },
          beforeShowPromise: () => waitForElement('.viewport-element'),
        },
        {
          id: 'pan',
          title: 'Panning the Image',
          text: 'You can pan the images using the middle click.',
          attachTo: {
            element: '.viewport-element',
            on: 'top',
          },
          advanceOn: {
            selector: '.cornerstone-viewport-element',
            event: 'CORNERSTONE_TOOLS_MOUSE_UP',
          },
          beforeShowPromise: () => waitForElement('.viewport-element'),
        },
        {
          id: 'windowing',
          title: 'Adjusting Window Level',
          text: 'You can modify the window level using the left click.',
          attachTo: {
            element: '.viewport-element',
            on: 'left',
          },
          advanceOn: {
            selector: '.cornerstone-viewport-element',
            event: 'CORNERSTONE_TOOLS_MOUSE_UP',
          },
          beforeShowPromise: () => waitForElement('.viewport-element'),
        },
        {
          id: 'length',
          title: 'Using the Measurement Tools',
          text: 'You can measure the length of a region using the Length tool.',
          attachTo: {
            element: '[data-cy="MeasurementTools-split-button-primary"]',
            on: 'bottom',
          },
          advanceOn: {
            selector: '[data-cy="MeasurementTools-split-button-primary"]',
            event: 'click',
          },
          beforeShowPromise: () =>
            waitForElement('[data-cy="MeasurementTools-split-button-primary]'),
        },
        {
          id: 'drawAnnotation',
          title: 'Drawing Length Annotations',
          text: 'Use the length tool on the viewport to measure the length of a region.',
          attachTo: {
            element: '.viewport-element',
            on: 'right',
          },
          advanceOn: {
            selector: 'body',
            event: 'event::measurement_added',
          },
          beforeShowPromise: () => waitForElement('.viewport-element'),
        },
        {
          id: 'trackMeasurement',
          title: 'Tracking Measurements in the Panel',
          text: 'Click yes to track the measurements in the measurement panel.',
          attachTo: {
            element: '[data-cy="prompt-begin-tracking-yes-btn"]',
            on: 'bottom',
          },
          advanceOn: {
            selector: '[data-cy="prompt-begin-tracking-yes-btn"]',
            event: 'click',
          },
          beforeShowPromise: () => waitForElement('[data-cy="prompt-begin-tracking-yes-btn"]'),
        },
        {
          id: 'openMeasurementPanel',
          title: 'Opening the Measurements Panel',
          text: 'Click the measurements button to open the measurements panel.',
          attachTo: {
            element: '#trackedMeasurements-btn',
            on: 'left-start',
          },
          advanceOn: {
            selector: '#trackedMeasurements-btn',
            event: 'click',
          },
          beforeShowPromise: () => waitForElement('#trackedMeasurements-btn'),
        },
        {
          id: 'scrollAwayFromMeasurement',
          title: 'Scrolling Away from a Measurement',
          text: 'Scroll the images using the mouse wheel away from the measurement.',
          attachTo: {
            element: '.viewport-element',
            on: 'left',
          },
          advanceOn: {
            selector: '.cornerstone-viewport-element',
            event: 'CORNERSTONE_TOOLS_MOUSE_WHEEL',
          },
          beforeShowPromise: () => waitForElement('.viewport-element'),
        },
        {
          id: 'jumpToMeasurement',
          title: 'Jumping to Measurements in the Panel',
          text: 'Click the measurement in the measurement panel to jump to it.',
          attachTo: {
            element: '[data-cy="data-row"]',
            on: 'left-start',
          },
          advanceOn: {
            selector: '[data-cy="data-row"]',
            event: 'click',
          },
          beforeShowPromise: () => waitForElement('[data-cy="data-row"]'),
        },
        {
          id: 'changeLayout',
          title: 'Changing Layout',
          text: 'You can change the layout of the viewer using the layout button.',
          attachTo: {
            element: '[data-cy="Layout"]',
            on: 'bottom',
          },
          advanceOn: {
            selector: '[data-cy="Layout"]',
            event: 'click',
          },
          beforeShowPromise: () => waitForElement('[data-cy="Layout"]'),
        },
        {
          id: 'selectLayout',
          title: 'Selecting the MPR Layout',
          text: 'Select the MPR layout to view the images in MPR mode.',
          attachTo: {
            element: '[data-cy="MPR"]',
            on: 'left-start',
          },
          advanceOn: {
            selector: '[data-cy="MPR"]',
            event: 'click',
          },
          beforeShowPromise: () => waitForElement('[data-cy="MPR"]'),
        },
      ],
      tourOptions: {
        useModalOverlay: true,
        defaultStepOptions: {
          buttons: [
            {
              text: 'Skip all',
              action() {
                this.complete();
              },
              secondary: true,
            },
          ],
        },
      },
    },
  ],
};

/*
  Narrow-screen toolbar (ohif/app:v3.9.2), down to a 320px viewport.

  The header row is `relative h-[48px]` holding four absolutely positioned
  groups: the logo at left-0, an empty secondary toolbar at a hard-coded
  left-[250px], the primary toolbar centred with `left-1/2 -translate-x-1/2`,
  and the patient info + settings menu at right-0.

  Absolute positioning means the centred toolbar sizes to its content, so on a
  phone it runs underneath the settings menu and its last buttons cannot be
  tapped. This version has no toolbar option in app-config (`toolbarSections`
  arrives in a later release), so below 640px the row becomes an ordinary flex
  layout: the toolbar takes whatever width is left over from the settings menu
  and scrolls horizontally. Using flex rather than a fixed right-hand reserve
  keeps it correct at 320px, where a guessed offset would be a few pixels out.

  The 48px header height is untouched — the viewport is sized as
  `calc(100vh - 52px)` and depends on it.

  Selectors use [class*=] to avoid escaping Tailwind's bracketed class names,
  and are tied to this OHIF version's markup — re-check them on an upgrade.
*/
(function addNarrowScreenToolbarStyles() {
  var row = 'div[class*="h-[48px]"]';
  var toolbar = row + ' > div[class*="left-1/2"]';
  var style = document.createElement('style');
  style.textContent = [
    '@media (max-width: 640px) {',
    '  ' + row + ' {',
    '    display: flex;',
    '    align-items: center;',
    '  }',
    '  ' + row + ' > div[class*="absolute"] {',
    '    position: static;',
    '    transform: none;',
    '  }',
    // The logo group is empty (whiteLabeling) and so is the secondary section,
    // but both still occupy width in a flex row.
    '  ' + row + ' > div[class*="left-0"],',
    '  ' + row + ' > div[class*="left-[250px]"] {',
    '    display: none;',
    '  }',
    '  ' + toolbar + ' {',
    '    flex: 1 1 auto;',
    '    min-width: 0;',
    '    overflow-x: auto;',
    '    overflow-y: hidden;',
    '    scrollbar-width: none;',
    '    -ms-overflow-style: none;',
    '  }',
    '  ' + toolbar + '::-webkit-scrollbar { display: none; }',
    // max-content lets the button row exceed the strip so it scrolls
    // instead of being squeezed.
    '  ' + toolbar + ' > div {',
    '    width: max-content;',
    '    justify-content: flex-start;',
    '  }',
    '  ' + row + ' div[class*="gap-[4px]"] {',
    '    justify-content: flex-start;',
    '    min-width: 0;',
    '  }',
    '  ' + row + ' > div[class*="right-0"] {',
    '    flex: 0 0 auto;',
    '  }',
    '}',
    // Collapsed side panels: SidePanel keeps a closed panel at its full
    // expanded width and hides it behind a negative margin, leaving a ~29px
    // strip with a 28px reveal bar and 22px icons — under the ~44px touch
    // target. Give the closed panel an explicit 44px box instead of adjusting
    // the margin, so nothing depends on the panel's expanded width. The
    // :has() only matches the closed state, so opening a panel restores its
    // own inline width.
    '@media (max-width: 640px) {',
    '  div:has(> [data-cy="side-panel-header-right"]) {',
    '    width: 44px !important;',
    '    max-width: 44px !important;',
    '    margin-right: 0 !important;',
    '  }',
    '  div:has(> [data-cy="side-panel-header-left"]) {',
    '    width: 44px !important;',
    '    max-width: 44px !important;',
    '    margin-left: 0 !important;',
    '  }',
    '  [data-cy^="side-panel-header-"] {',
    '    min-height: 44px !important;',
    '    justify-content: center !important;',
    '    padding-left: 0 !important;',
    '    padding-right: 0 !important;',
    '  }',
    '  [data-cy^="side-panel-header-"] + div > * {',
    '    display: flex;',
    '    align-items: center;',
    '    justify-content: center;',
    '    min-height: 44px;',
    '    width: 100%;',
    '  }',
    '  [data-cy^="side-panel-header-"] + div [data-cy$="-btn"] svg {',
    '    width: 26px !important;',
    '    height: 26px !important;',
    '  }',
    '}',
  ].join('\n');
  document.head.appendChild(style);
})();

function waitForElement(selector, maxAttempts = 20, interval = 25) {
  return new Promise(resolve => {
    let attempts = 0;

    const checkForElement = setInterval(() => {
      const element = document.querySelector(selector);

      if (element || attempts >= maxAttempts) {
        clearInterval(checkForElement);
        resolve();
      }

      attempts++;
    }, interval);
  });
}
