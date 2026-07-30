import collectRss from "./collect-rss.mjs";

export default async function handler(request, context) {
  return collectRss(request, context);
}
