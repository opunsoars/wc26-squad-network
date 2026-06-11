window.addEventListener("load", () => {
  const data = window._wc26TeamData;
  if (!data) return;

  const nodes = data.players.map(p => ({
    id: p.tm_id,
    name: p.name,
    freshness: p.freshness_minutes,
    position: p.position,
  }));
  const links = data.edges.map(e => ({
    source: e.source,
    target: e.target,
    value: e.weighted_shared_minutes,
    raw: e.raw_shared_minutes,
  }));

  const svgEl = document.getElementById("network");
  const rect = svgEl.getBoundingClientRect();
  const width = rect.width || 860;
  const height = 500;

  const svg = d3.select("#network");

  if (links.length === 0) {
    svg.append("text")
      .attr("x", width / 2).attr("y", height / 2)
      .attr("text-anchor", "middle")
      .style("fill", "#8b949e").style("font-size", "14px")
      .text("No co-play edges for this squad");
    return;
  }

  const maxVal = d3.max(links, d => d.value) || 1;
  const strokeScale = d3.scaleLinear().domain([0, maxVal]).range([0.5, 6]);

  const maxFresh = d3.max(nodes, d => d.freshness) || 1;
  const rScale = d3.scaleSqrt().domain([0, maxFresh]).range([4, 14]);

  const posColor = { GK: "#f0b429", DF: "#4dabf7", MF: "#69db7c", FW: "#ff6b6b" };

  const sim = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(d => d.id).strength(d => (d.value / maxVal) * 0.4))
    .force("charge", d3.forceManyBody().strength(-120))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collision", d3.forceCollide(18));

  const link = svg.append("g").selectAll("line").data(links).join("line")
    .attr("class", "link")
    .attr("stroke-width", d => strokeScale(d.value));

  const node = svg.append("g").selectAll("g").data(nodes).join("g")
    .attr("class", "node")
    .call(
      d3.drag()
        .on("start", (event, d) => { if (!event.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
        .on("end", (event, d) => { if (!event.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
    );

  node.append("circle")
    .attr("r", d => rScale(d.freshness))
    .attr("fill", d => posColor[d.position] || "#8b949e")
    .attr("fill-opacity", 0.85);

  node.append("text")
    .attr("dy", "0.35em")
    .attr("text-anchor", "middle")
    .style("font-size", "9px")
    .text(d => d.name.split(" ").slice(-1)[0]);

  const tooltip = d3.select("body").append("div")
    .style("position", "absolute")
    .style("background", "#161b22")
    .style("border", "1px solid #30363d")
    .style("border-radius", "4px")
    .style("padding", "0.5rem 0.75rem")
    .style("font-size", "12px")
    .style("pointer-events", "none")
    .style("opacity", 0);

  node
    .on("mouseover", (event, d) => {
      tooltip.transition().duration(150).style("opacity", 1);
      tooltip.html(`<strong>${d.name}</strong><br/>${d.position} · ${d.freshness} min`)
        .style("left", `${event.pageX + 10}px`)
        .style("top", `${event.pageY - 10}px`);
    })
    .on("mouseout", () => tooltip.transition().duration(150).style("opacity", 0));

  sim.on("tick", () => {
    link
      .attr("x1", d => d.source.x).attr("y1", d => d.source.y)
      .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
    node.attr("transform", d => `translate(${d.x},${d.y})`);
  });
});
