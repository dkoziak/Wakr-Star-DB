Title: Data Architecture Review v2
# Goal
- We have a new design of the UX for the analytics package for Wakr (https://shirt-relate-26267719.figma.site/inventory).  Review this design & compare to existing erd in wakr_data_architecture.json and update (same file name, post-pend _v2) as required.
# Special Nbtes
- Review the tableds Inventory, Regional, Pricing.  Skip Dealers, as it is not yet implemented.
- Ignore the suggested text based observations.  We will deal with those in a later prompt.
- Look at all graphs and boxes containing a metric.
- Look at the various parameters (Time Range, Inventory Type, etc).
- Assume we will add Model (values defined by Make) as a parameter to all pages
- Assume that for every metric box we include a comparison % metric > or < 0% of the current user's company (Make & or model) to the other Makes

