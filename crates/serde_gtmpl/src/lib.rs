use serde::{de::DeserializeOwned, Serialize};
use serde_json::json;

pub trait ToGtmplValue {
    fn to_gtmpl_value(&self) -> gtmpl_value::Value;
}

fn json_to_gtmpl_value(json: &serde_json::Value) -> gtmpl_value::Value {
    match json {
        serde_json::Value::Null => unimplemented!(),
        serde_json::Value::Bool(b) => (*b).into(),
        serde_json::Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                return gtmpl_value::Value::Number(i.into());
            } else if let Some(u) = n.as_u64() {
                return gtmpl_value::Value::Number(u.into());
            } else if let Some(f) = n.as_f64() {
                return gtmpl_value::Value::Number(f.into());
            }

            unimplemented!()
        }
        serde_json::Value::String(s) => s.into(),
        serde_json::Value::Array(arr) => arr
            .iter()
            .map(json_to_gtmpl_value)
            .collect::<Vec<_>>()
            .into(),
        serde_json::Value::Object(map) => {
            let mut object = map
                .iter()
                .map(|(k, v)| (k.clone(), json_to_gtmpl_value(v)))
                .collect::<std::collections::HashMap<_, _>>();

            // XXX(mnaser): This is stinky, but we only use this in test anyways.
            object.insert(
                "builtin".to_string(),
                gtmpl_value::Value::Object(
                    vec![(
                        "cluster".to_string(),
                        gtmpl_value::Value::Object(
                            vec![
                                (
                                    "name".to_string(),
                                    gtmpl_value::Value::String("kube-abcde".to_string()),
                                ),
                                (
                                    "namespace".to_string(),
                                    gtmpl_value::Value::String("magnum-system".to_string()),
                                ),
                            ]
                            .into_iter()
                            .collect(),
                        ),
                    )]
                    .into_iter()
                    .collect(),
                ),
            );

            gtmpl_value::Value::Object(object)
        }
    }
}

impl<T: Serialize + DeserializeOwned> ToGtmplValue for T {
    fn to_gtmpl_value(&self) -> gtmpl_value::Value {
        let json = json!(self);
        json_to_gtmpl_value(&json)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_to_gtmpl_value() {
        let s = "hello".to_string();
        let v = s.to_gtmpl_value();
        assert_eq!(v, gtmpl_value::Value::String("hello".to_string()));

        let n = 42;
        let v = n.to_gtmpl_value();
        assert_eq!(v, gtmpl_value::Value::Number(42.into()));

        let b = true;
        let v = b.to_gtmpl_value();
        assert_eq!(v, gtmpl_value::Value::Bool(true));

        let arr = vec![1, 2, 3];
        let v = arr.to_gtmpl_value();
        assert_eq!(
            v,
            gtmpl_value::Value::Array(vec![
                gtmpl_value::Value::Number(1.into()),
                gtmpl_value::Value::Number(2.into()),
                gtmpl_value::Value::Number(3.into())
            ])
        );
    }
}
