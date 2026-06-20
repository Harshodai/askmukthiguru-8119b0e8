const fs = require('fs');
const { execSync } = require('child_process');
const path = require('path');

const projectRoot = '/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8';
const pluginRoot = '/Users/harshodaikolluru/.claude/plugins/cache/understand-anything/understand-anything/2.7.7';

const computeBatchesScript = path.join(pluginRoot, 'skills/understand/compute-batches.mjs');
const extractStructureScript = path.join(pluginRoot, 'skills/understand/extract-structure.mjs');
const mergeBatchGraphsScript = path.join(pluginRoot, 'skills/understand/merge-batch-graphs.py');
const buildFingerprintsScript = path.join(pluginRoot, 'skills/understand/build-fingerprints.mjs');

const intermediateDir = path.join(projectRoot, '.understand-anything/intermediate');
const tmpDir = path.join(projectRoot, '.understand-anything/tmp');
const pythonPath = '/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/.venv/bin/python';

const fileToCategory = {};

function mapCategory(category) {
  switch (category) {
    case 'docs':
      return { type: 'document', prefix: 'document:' };
    case 'config':
      return { type: 'config', prefix: 'config:' };
    case 'infra':
      return { type: 'service', prefix: 'service:' };
    case 'data':
      return { type: 'table', prefix: 'table:' };
    case 'code':
    case 'script':
    case 'markup':
    default:
      return { type: 'file', prefix: 'file:' };
  }
}

function getFileNodeId(filePath, category) {
  const cat = category || fileToCategory[filePath];
  const { prefix } = mapCategory(cat);
  return `${prefix}${filePath}`;
}

async function run() {
  const metaPath = path.join(projectRoot, '.understand-anything/meta.json');
  const graphPath = path.join(projectRoot, '.understand-anything/knowledge-graph.json');
  
  const currentCommit = execSync('git rev-parse HEAD').toString().trim();
  
  let isIncremental = false;
  let lastCommit = '';
  const forceFull = process.argv.includes('--full');
  
  if (!forceFull && fs.existsSync(metaPath) && fs.existsSync(graphPath)) {
    try {
      const meta = JSON.parse(fs.readFileSync(metaPath, 'utf8'));
      lastCommit = meta.gitCommitHash;
      if (lastCommit && lastCommit !== currentCommit) {
        isIncremental = true;
      } else if (lastCommit === currentCommit) {
        console.log('Knowledge graph is already up to date at commit', currentCommit);
        return;
      }
    } catch (err) {
      console.warn('Could not read metadata, falling back to full rebuild:', err.message);
    }
  }
  
  fs.mkdirSync(intermediateDir, { recursive: true });
  fs.mkdirSync(tmpDir, { recursive: true });
  
  let changedFiles = [];
  
  if (isIncremental) {
    console.log(`Incremental update: Diffing from ${lastCommit} to ${currentCommit}...`);
    try {
      const diffOutput = execSync(`git diff ${lastCommit}..HEAD --name-only`).toString().trim();
      changedFiles = diffOutput ? diffOutput.split('\n') : [];
    } catch (err) {
      console.warn('Git diff failed, falling back to full rebuild:', err.message);
      isIncremental = false;
    }
  }
  
  if (isIncremental && changedFiles.length === 0) {
    console.log('No files changed since last analysis.');
    return;
  }
  
  if (!isIncremental) {
    console.log('Full rebuild triggered.');
  } else {
    console.log(`Changed files count: ${changedFiles.length}`);
  }
  
  // 1. Scan project to get current files inventory
  console.log('Scanning project files...');
  const scanResultPath = path.join(intermediateDir, 'scan-result.json');
  
  // We run scan-project.mjs to build the raw files list
  const rawScanPath = path.join(tmpDir, 'ua-scan-files.json');
  execSync(`node "${path.join(pluginRoot, 'skills/understand/scan-project.mjs')}" "${projectRoot}" "${rawScanPath}"`);
  
  // Extract imports
  const importMapInputPath = path.join(tmpDir, 'ua-import-map-input.json');
  const importMapOutputPath = path.join(tmpDir, 'ua-import-map-output.json');
  const scanFiles = JSON.parse(fs.readFileSync(rawScanPath, 'utf8'));
  
  for (const f of scanFiles.files) {
    fileToCategory[f.path] = f.fileCategory;
  }
  
  fs.writeFileSync(importMapInputPath, JSON.stringify({
    projectRoot,
    files: scanFiles.files
  }, null, 2));
  
  execSync(`node "${path.join(pluginRoot, 'skills/understand/extract-import-map.mjs')}" "${importMapInputPath}" "${importMapOutputPath}"`);
  
  // Assemble scan-result.json
  const importMapOut = JSON.parse(fs.readFileSync(importMapOutputPath, 'utf8'));
  const scanResult = {
    name: "askmukthiguru",
    description: "An AI-powered spiritual guide rooted in the teachings of Sri Preethaji & Sri Krishnaji. Built with a multi-layer RAG pipeline, real-time guardrails, and beautiful conversational UI.",
    languages: ["bash", "css", "html", "javascript", "json", "jsonc", "markdown", "python", "sql", "typescript", "yaml"],
    frameworks: ["React", "Vite", "TailwindCSS", "FastAPI", "Supabase", "Qdrant", "Neo4j", "Docker", "GitHub Actions"],
    files: scanFiles.files,
    totalFiles: scanFiles.totalFiles,
    filteredByIgnore: scanFiles.filteredByIgnore,
    estimatedComplexity: scanFiles.estimatedComplexity,
    importMap: importMapOut.importMap
  };
  fs.writeFileSync(scanResultPath, JSON.stringify(scanResult, null, 2), 'utf8');
  
  // 2. Compute batches
  console.log('Computing batches...');
  let computeBatchesCmd = `node "${computeBatchesScript}" "${projectRoot}"`;
  if (isIncremental) {
    const changedFilesListPath = path.join(tmpDir, 'changed-files.txt');
    fs.writeFileSync(changedFilesListPath, changedFiles.join('\n'), 'utf8');
    computeBatchesCmd += ` --changed-files="${changedFilesListPath}"`;
  }
  execSync(computeBatchesCmd);
  
  const batchesData = JSON.parse(fs.readFileSync(path.join(intermediateDir, 'batches.json'), 'utf8'));
  const batches = batchesData.batches;
  console.log(`Processing ${batches.length} batches.`);
  
  // Process computed batches
  const concurrency = 10;
  for (let i = 0; i < batches.length; i += concurrency) {
    const chunk = batches.slice(i, i + concurrency);
    const promises = chunk.map(async (batch) => {
      const batchIndex = batch.batchIndex;
      const batchInput = {
        projectRoot,
        batchFiles: batch.files,
        batchImportData: batch.batchImportData
      };
      
      const inputPath = path.join(tmpDir, `batch-${batchIndex}-input.json`);
      const outputPath = path.join(tmpDir, `batch-${batchIndex}-output.json`);
      fs.writeFileSync(inputPath, JSON.stringify(batchInput, null, 2), 'utf8');
      
      try {
        execSync(`node "${extractStructureScript}" "${inputPath}" "${outputPath}"`, { stdio: 'ignore' });
      } catch (err) {
        console.error(`Error in batch ${batchIndex}:`, err.message);
        return;
      }
      
      if (!fs.existsSync(outputPath)) return;
      const structure = JSON.parse(fs.readFileSync(outputPath, 'utf8'));
      
      const nodes = [];
      const edges = [];
      
      for (const res of structure.results) {
        const { type: fileType, prefix: filePrefix } = mapCategory(res.fileCategory);
        const fileId = `${filePrefix}${res.path}`;
        nodes.push({
          id: fileId,
          type: fileType,
          name: path.basename(res.path),
          filePath: res.path,
          summary: `Source file containing code, configuration, or documentation. Path: ${res.path}`,
          tags: [res.language, res.fileCategory],
          complexity: res.totalLines < 150 ? 'simple' : (res.totalLines < 500 ? 'moderate' : 'complex'),
          languageNotes: `${res.language} file`
        });
        
        if (res.classes) {
          for (const cls of res.classes) {
            const classId = `class:${res.path}:${cls.name}`;
            nodes.push({
              id: classId,
              type: 'class',
              name: cls.name,
              filePath: res.path,
              summary: `Class ${cls.name} defined in ${res.path}`,
              tags: ['class', res.language],
              complexity: 'moderate',
              languageNotes: ''
            });
            edges.push({ source: fileId, target: classId, type: 'contains', direction: 'forward', weight: 1.0, description: 'Contains class' });
          }
        }
        
        if (res.functions) {
          for (const fn of res.functions) {
            const funcId = `function:${res.path}:${fn.name}`;
            nodes.push({
              id: funcId,
              type: 'function',
              name: fn.name,
              filePath: res.path,
              summary: `Function ${fn.name} defined in ${res.path}`,
              tags: ['function', res.language],
              complexity: 'simple',
              languageNotes: ''
            });
            edges.push({ source: fileId, target: funcId, type: 'contains', direction: 'forward', weight: 1.0, description: 'Contains function' });
          }
        }
        
        const imports = batch.batchImportData?.[res.path] || [];
        for (const imp of imports) {
          edges.push({ source: fileId, target: getFileNodeId(imp), type: 'imports', direction: 'forward', weight: 0.8, description: `Imports ${imp}` });
        }
      }
      
      const batchGraph = { nodes, edges };
      fs.writeFileSync(path.join(intermediateDir, `batch-${batchIndex}.json`), JSON.stringify(batchGraph, null, 2), 'utf8');
    });
    
    await Promise.all(promises);
  }
  
  // 3. Handle incremental merging
  if (isIncremental) {
    console.log('Pruning existing nodes for changed files...');
    const existingGraph = JSON.parse(fs.readFileSync(graphPath, 'utf8'));
    const changedFilesSet = new Set(changedFiles);
    
    // Filter out old nodes for changed files
    const prunedNodes = (existingGraph.nodes || []).filter(node => {
      return !changedFilesSet.has(node.filePath);
    });
    
    // Gather surviving node IDs
    const survivingNodeIds = new Set(prunedNodes.map(n => n.id));
    
    // Filter out edges referring to removed nodes
    const prunedEdges = (existingGraph.edges || []).filter(edge => {
      return survivingNodeIds.has(edge.source) && survivingNodeIds.has(edge.target);
    });
    
    fs.writeFileSync(
      path.join(intermediateDir, 'batch-existing.json'),
      JSON.stringify({ nodes: prunedNodes, edges: prunedEdges }, null, 2),
      'utf8'
    );
    console.log(`Pruned graph contains ${prunedNodes.length} nodes and ${prunedEdges.length} edges.`);
  }
  
  // 4. Merge
  console.log('Merging graphs...');
  execSync(`"${pythonPath}" "${mergeBatchGraphsScript}" "${projectRoot}"`);
  
  // 5. Finalize assembled graph (layers, tour, validation)
  const assembledGraph = JSON.parse(fs.readFileSync(path.join(intermediateDir, 'assembled-graph.json'), 'utf8'));
  const nodes = assembledGraph.nodes || [];
  const edges = assembledGraph.edges || [];
  const nodeIds = new Set(nodes.map(n => n.id));
  
  const fileLevelTypes = new Set(['file', 'config', 'document', 'service', 'pipeline', 'table', 'schema', 'resource', 'endpoint']);
  const frontendIds = [];
  const backendApiIds = [];
  const ragPipelineIds = [];
  const ingestionIds = [];
  const configIds = [];
  
  nodes.forEach(node => {
    if (!fileLevelTypes.has(node.type)) return;
    const filePath = node.filePath || '';
    if (filePath.startsWith('src/') || filePath.startsWith('public/') || filePath === 'index.html') {
      frontendIds.push(node.id);
    } else if (filePath.startsWith('backend/app/') || filePath.startsWith('backend/routers/') || filePath.startsWith('backend/api/') || filePath.startsWith('backend/models/') || filePath.startsWith('backend/services/auth_service.py')) {
      backendApiIds.push(node.id);
    } else if (filePath.startsWith('backend/rag/') || filePath.startsWith('backend/guardrails/')) {
      ragPipelineIds.push(node.id);
    } else if (filePath.startsWith('backend/ingest/') || filePath.startsWith('backend/scripts/') || filePath.startsWith('scripts/')) {
      ingestionIds.push(node.id);
    } else {
      configIds.push(node.id);
    }
  });
  
  const layers = [
    { id: "layer:frontend", name: "Frontend UI", description: "Vite React SPA and static assets served via Nginx", nodeIds: frontendIds },
    { id: "layer:backend-api", name: "Backend FastAPI", description: "App routing, authentication, and core API singletons", nodeIds: backendApiIds },
    { id: "layer:rag-pipeline", name: "RAG & Guardrails", description: "Multi-layer RAG logic, intent routers, and safety handlers", nodeIds: ragPipelineIds },
    { id: "layer:ingestion", name: "Ingestion Pipeline", description: "ETL loaders, chunking strategies, and vector DB insertion scripts", nodeIds: ingestionIds },
    { id: "layer:configuration", name: "Configuration & Infrastructure", description: "Docker, Kubernetes, package manifests, and repository setup", nodeIds: configIds }
  ];
  
  const tourCandidates = [
    { order: 1, title: "Welcome to AskMukthiGuru", description: "Start with the project README to get a high-level overview of the AI spiritual guide's architecture, ports, and setup instructions.", nodeIds: ["document:README.md"] },
    { order: 2, title: "FastAPI Application Core", description: "This is the entry point of the FastAPI backend. It mounts the routers, registers lifecycle hooks, and initializes dependencies.", nodeIds: ["file:backend/app/main.py"] },
    { order: 3, title: "The 12-Layer RAG Pipeline", description: "FastAPI backend coordinates query analysis, intent routing, and verification strategies through a 12-layer pipeline.", nodeIds: ["file:backend/rag/graph_strategies.py"] },
    { order: 4, title: "Vite React Frontend", description: "The client-side interface is a highly premium Vite React 18 single-page application.", nodeIds: ["file:src/App.tsx", "file:src/components/chat/ChatInterface.tsx"] }
  ];
  
  const tour = tourCandidates.map(step => {
    return { ...step, nodeIds: step.nodeIds.filter(id => nodeIds.has(id)) };
  }).filter(step => step.nodeIds.length > 0);
  
  const finalGraph = {
    version: "1.0.0",
    project: {
      name: "askmukthiguru",
      languages: ["bash", "css", "html", "javascript", "json", "jsonc", "markdown", "python", "sql", "typescript", "yaml"],
      frameworks: ["React", "Vite", "TailwindCSS", "FastAPI", "Supabase", "Qdrant", "Neo4j", "Docker", "GitHub Actions"],
      description: "An AI-powered spiritual guide rooted in the teachings of Sri Preethaji & Sri Krishnaji. Built with a multi-layer RAG pipeline, real-time guardrails, and beautiful conversational UI.",
      analyzedAt: new Date().toISOString(),
      gitCommitHash: currentCommit
    },
    nodes,
    edges,
    layers,
    tour
  };
  
  fs.writeFileSync(graphPath, JSON.stringify(finalGraph, null, 2), 'utf8');
  
  // 6. Fingerprints & Meta
  console.log('Generating fingerprints baseline...');
  const fingerprintInput = {
    projectRoot,
    sourceFilePaths: scanResult.files.map(f => f.path),
    gitCommitHash: currentCommit
  };
  const fingerprintInputPath = path.join(intermediateDir, 'fingerprint-input.json');
  fs.writeFileSync(fingerprintInputPath, JSON.stringify(fingerprintInput, null, 2), 'utf8');
  
  execSync(`node "${buildFingerprintsScript}" "${fingerprintInputPath}"`);
  
  const meta = {
    lastAnalyzedAt: finalGraph.project.analyzedAt,
    gitCommitHash: currentCommit,
    version: "1.0.0",
    analyzedFiles: scanResult.totalFiles
  };
  fs.writeFileSync(metaPath, JSON.stringify(meta, null, 2), 'utf8');
  
  // Cleanup
  console.log('Cleaning up intermediate files...');
  const trashDir = path.join(projectRoot, `.understand-anything/.trash-${Math.floor(Date.now() / 1000)}`);
  fs.mkdirSync(trashDir, { recursive: true });
  fs.readdirSync(intermediateDir).forEach(file => {
    if (file !== 'scan-result.json') {
      fs.renameSync(path.join(intermediateDir, file), path.join(trashDir, file));
    }
  });
  if (fs.existsSync(tmpDir)) {
    fs.renameSync(tmpDir, path.join(trashDir, 'tmp'));
  }
  
  console.log(`Knowledge graph updated successfully. Total: ${nodes.length} nodes, ${edges.length} edges.`);
}

run().catch(console.error);
