import html from "./snapshot.html";

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === "/stocks" || url.pathname === "/stocks/") {
      return new Response(html, {
        headers: { "content-type": "text/html; charset=utf-8", "cache-control": "public, max-age=300", "x-robots-tag": "noindex" },
      });
    }
    return Response.redirect(`${url.origin}/stocks`, 302);
  },
};
